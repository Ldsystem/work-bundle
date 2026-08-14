---
name: wb-initialize-project
description: Initialize, validate, doctor, or migrate single- and multi-repository WorkBundle workspaces via scripts/wb.py dispatcher commands.
---

# wb-initialize-project

## Purpose

Initialize, doctor, validate, register, inspect, or migrate a project as a work-bundle adapted workspace using mechanical dispatcher commands only.

## Inputs

- `workspace_root`: authority root that owns `.work-bundle/`, `AGENTS.md`, `script/`, and `credentials/`; in multi-repository mode it also owns managed members.
- `project_root`: one concrete source repository checkout; equal to `workspace_root` in single-repository mode and a member path in multi-repository mode.
- Explicit `mode`: `single-repository` or `multi-repository` for new initialization.
- `~/.work-bundle/bootstrap.yaml` for `project_registry` and `work_bundle_root` resolution.
- `~/.work-bundle/bootstrap.yaml` field `prefer_subagent` for the global sub-agent scheduling preference default.
- `$workspace_root/.work-bundle/project.yaml` field `prefer_subagent` for the current workspace override.
- Optional `WB_WORK_BUNDLE_ROOT` environment override when the agent must pass an explicit toolkit root to dispatcher commands.
- Work-bundle reference templates and manifests under the bootstrap-resolved work-bundle root:
  - `references/assets/template/project.yaml`
  - `references/assets/template/projects.yaml`
  - `references/assets/template/AGENTS.md`
  - `references/wb-initialize-project-default-work-bundle-tree.yaml`
- Git CLI for mechanical repository capability, branch, and HEAD-commit inspection when the project root is Git-backed.
- Optional `.codegraph/` marker under each source repository; absence means CodeGraph is unsupported for that repository and must be reported as `no-index`, not initialized.

## Must

Invoke project lifecycle behavior only through `python3 scripts/wb.py` dispatcher commands. Do not create, modify, or validate `scripts/work-bundle/project.py` or other script modules from this skill.

| Mode | Command |
|---|---|
| Initialize | `init-project <root> --mode <single-repository|multi-repository> [--workspace-root <workspace-root>] [--project-root <project-root>] [--name <name>] [--force] [--dry-run] [--disable-work-bundle-git] [--create-project-skill-override]` |
| Doctor | `doctor-project <root> [--workspace-root <workspace-root>] [--project-root <project-root>] [--repair] [--force]` |
| Inspect only | `show-project [--workspace-root <workspace-root> | --project-root <project-root>]` |
| Strict validate | `validate-project <root> [--workspace-root <workspace-root>] [--project-root <project-root>] [--dry-run]` |
| Register only | `register-project <root> [--workspace-root <workspace-root>] [--project-root <project-root>] [--name <name>]` |
| Inspect metadata migration | `migrate-project <root> [--name <name>] --dry-run` |
| Apply metadata migration | `migrate-project <root> [--name <name>] [--force] [--accepted-proposal-id <id>] --apply` |
| Inspect portable-control migration | `migrate-control-plane <workspace-root> [--repository-remote <id>=<canonical-remote>] --dry-run` |
| Apply portable-control migration | `migrate-control-plane <workspace-root> [--repository-remote <id>=<canonical-remote>] --accepted-proposal-id <id> --apply` |
| Attach portable workspace | `attach-workspace <workspace-root> [--materialize <none|missing|all>] [--repository-path <id>=<path>] (--dry-run|--apply)` |
| Doctor portable workspace | `doctor-workspace <workspace-root> [--repair]` |
| Provision member | `provision-member --workspace-root <workspace-root> [--workspace-slug <slug>] --origin <origin-root> --repository-id <id> --working-branch <branch> --base-ref <ref> [--dry-run|--apply]` |
| Cleanup member | `cleanup-member --workspace-root <workspace-root> --repository-id <id> (--dry-run|--apply)` |
| Set sub-agent preference | `set-prefer-subagent <true|false|enable|disable|on|off> --scope <global|project> [--project-root <project-root>]` |

`initialize-project` remains a compatibility alias for `init-project`; prefer `init-project` in new instructions.

Existing command names and `--project-root` remain supported for single-repository projects. New creation must reject a missing or contradictory mode/root combination rather than silently infer topology. Single-repository mode is current and fully supported, not legacy or transitional.

**Portable v4 migration guardrails:** before `migrate-control-plane`, load every applicable rule body in full, including project context, registry authority, lifecycle, repository boundary, security exclusion, and violation routing. Do not sample those rules by keyword. Resolve canonical remotes from explicit `--repository-remote` input, registry locator authority, and the live origin chain. When authoritative network remotes conflict, stop and ask the user which remote is canonical; rerun the exact dry-run with `--repository-remote` after the decision. During this workflow, do not edit the project registry directly and do not change an external repository's Git config. `show-project`, `validate-project`, and `doctor-project` route metadata-version-4 workspaces to v4 control-plane validation; repair must never rewrite portable v4 metadata into v3 shape.

**Preserve behavior (default):** commands preserve existing non-empty files and user-authored `AGENTS.md` content outside the WorkBundle managed section. Re-running `init-project` on a healthy project reports `changed_files: []`.

**`init-project --force`:** may overwrite init-managed template files only: `.work-bundle/project.yaml`, `.work-bundle/rules/index.yaml`, `.work-bundle/knowledge/project.yaml`. For `AGENTS.md`, force refreshes only the WorkBundle managed section from `references/assets/template/AGENTS.md` and preserves user-authored content outside that section.

**`migrate-project --force`:** narrower migration-only repair subset; overwrites `.work-bundle/project.yaml` only. For `AGENTS.md`, migration may convert legacy whole-file template content or stale managed sections to the current marker-bounded managed section without taking ownership of the whole file.

For metadata v2, `migrate-project --dry-run` classifies topology from project metadata plus the bootstrap-resolved registry and returns a proposal ID. In-place apply is allowed only for `single-compatible` evidence and requires that exact ID. Multiple repository locators route to `migrate-to-multi-repository`; registry/metadata identity conflicts and proposal drift fail closed. `--force` never overrides topology classification.

`provision-member --dry-run` returns `status: proposed` without writes. Apply treats checkout verification as an internal state and returns `status: passed` only after the member binding and origin locator are recoverably published to workspace metadata and the project registry. Matching verified transactions resume publication, published transactions replay without writes, and unrelated targets remain collisions.

An exact workspace-local checkout created by an older WorkBundle version may have no recovery record. `provision-member` adopts it only when control scope, origin, repository ID, branch, and base HEAD all match; dry-run reports `resume_source: verified-orphan`. It never claims that adopted checkout as rollback-owned. `cleanup-member` is limited to recorded, unpublished, transaction-owned checkouts; published members require a separate deregistration workflow and unrecorded paths are never deleted.

**`init-project --dry-run` / `validate-project --dry-run`:** inspect and report mechanical failures without writing project files.

**`prefer_subagent` management:**

- `prefer_subagent` is a boolean preference only; it does not bypass orchestration preflight, dependency, write-scope, handoff, or fallback rules.
- Effective value resolves as project metadata first, then global bootstrap, then `false`:
  - project: `$workspace_root/.work-bundle/project.yaml` -> `prefer_subagent`;
  - global: `$work_bundle_config_root/bootstrap.yaml` -> `prefer_subagent`;
  - default: `false`.
- Use `set-prefer-subagent true --scope global` for requests such as "Enable global `prefer_subagent`".
- Use `set-prefer-subagent false --scope global` for requests such as "Disable global `prefer_subagent`".
- Use `set-prefer-subagent false --scope project --project-root <project-root>` for requests such as "Disable `prefer_subagent` for current workspace".
- Use `set-prefer-subagent true --scope project --project-root <project-root>` for requests such as "Enable `prefer_subagent` for current workspace".
- The command updates only the selected YAML file and reports `target_path`, `changed_files`, and `effective_prefer_subagent` in JSON.
- Do not hand-edit either YAML file for this preference when the dispatcher command is available.

**Registry and slug (per `wb-project-registry`):**

- Resolve the project registry path from `bootstrap.yaml` field `project_registry`.
- Register every initialized project to `projects.yaml` as a new workspace slug or an existing workspace slug.
- Derive the workspace slug from `--name` when provided; otherwise from the project root directory name (normalized lowercase alphanumeric with hyphens).
- On slug or workspace-root match, merge registry entries and preserve existing aliases, origins, compatibility locators, and unknown fields unless explicitly replaced.
- Keep the registry locator-oriented. It owns workspace slug/root and stable repository origin `id`, `origin_path`, `remote`, and Git capability; it does not own member path, expected branch, observed HEAD, cleanliness, lifecycle transaction, operation policy, or CodeGraph state.
- Model origins and workspace members independently. Multiple workspaces may register the same origin ID while owning independent local control stores, named worktrees, and distinct working branches.
- Preserve every registered origin/member identity and unknown field during initialize, repair, registration, and migration; never collapse multi-member state to the command cwd.
- When registering an origin or provisioning a member, update the bootstrap-resolved registry and `$workspace_root/.work-bundle/project.yaml` atomically or recoverably, publishing active state only after verification.
- Treat public member-provision success as a converged state: workspace-local checkout verified, metadata member published, and registry origin published. Never report success with pending publication states.
- Carry a short role description in registry output/templates and workspace metadata: registry is locator-only; workspace metadata is working-state authority.
- Ask for the workspace slug decision only when it is missing and blocking.

**Workspace metadata v3 and v2 compatibility:**

- Render new or explicitly migrated `.work-bundle/project.yaml` with `metadata_version: 3`, `workspace_root`, explicit `workspace_mode`, workspace resource status, operation policy, and member bindings.
- Keep `.work-bundle/project.yaml` as workspace-local authority for member working state, expected branch/base ref, observed HEAD/time, lifecycle state, operation policy, and CodeGraph state.
- Read metadata v2 during the compatibility window, preserve unknown fields, and require inspect/dry-run/explicit apply before converting topology or moving worktrees.
- Render `operation_policy.project_files` with non-destructive file operations and `operation_policy.git` with allowed read operations, permissive stage/commit/pull operations, and forbidden destructive operations including `reset --hard`, `clean -fd`, and `push --force`.
- Render v3 `source_repositories[]` members with stable `id`, `project_root`, `origin_id`, checkout kind, workspace-local control-store binding, worktree name, expected branch, base ref, observed HEAD/time, baseline/lifecycle status, operation policy, and nested CodeGraph state.
- In single-repository mode require `workspace_root == project_root`; do not silently alter its existing Git tracking policy.
- In canonical multi-repository mode require each managed `project_root` and absolute Git common directory to remain beneath `workspace_root`.
- For Git-backed repositories, mechanically record live branch and HEAD as observations; keep expected branch/base ref as declared policy and provision input.
- For non-Git repositories, set `git_repository: false`, `branch_required: false`, empty `last_commit_id`, and `baseline_status: not-git`.
- For repositories without `.codegraph/`, set `codegraph.supported: false`, `codegraph.index_present: false`, `codegraph.status: not-indexed`, and `codegraph.reason: no-index`. Do not run `codegraph init` or `codegraph sync`.
- For repositories with `.codegraph/`, report marker presence only; synchronization remains owned by orchestration review behavior, not initialization.

**Initialization structure:**

- Create `$workspace_root/.work-bundle/knowledge/{context-packs,indexes,notes,open-questions}`.
- Create the full `.work-bundle/orchestration` subtree at initialization:
  - `orchestration/spec/{active,archived}`
  - `orchestration/plan/{active,archived}`
  - `orchestration/handoff/orchestration/{active,archived}`
  - `orchestration/handoff/executor/{active,archived}`
  - `orchestration/{docs,principles,templates,reviews,execution-state}`
- Directory membership is driven by `references/wb-initialize-project-default-work-bundle-tree.yaml`.
- In both workspace modes, create or preserve `$workspace_root/script/index.yaml` from its empty v1 template and never auto-execute indexed utilities.
- In both workspace modes, create or preserve `$workspace_root/credentials/credentials.yaml` as the sole credential-directory file, enforce protection, and keep the directory Git-ignored without reading values.
- In both workspace modes, render and validate the `workspace_resources` metadata block. In single-repository mode, keep `script/` available to the source repository's established tracking policy while excluding `credentials/` and `.work-bundle/` without replacing existing ignore content or untracking user-owned paths.
- In multi-repository mode place runtime Git control stores beneath `$workspace_root/.work-bundle/git/` and exclude them from workspace-management commits and broad scans.
- Render `.work-bundle/project.yaml` from `references/assets/template/project.yaml`.
- Render `.work-bundle/project.yaml` with metadata v3 workspace/member state from mechanical Git and per-member `.codegraph/` inspection.
- Render `.work-bundle/project.yaml` with a `prefer_subagent: false` default unless a future template version explicitly changes the default.
- Render `.work-bundle/project.yaml` with an `agents_sync` section that owns WorkBundle `AGENTS.md` checksum and sync-status state.
- Create, append, or refresh `AGENTS.md` with the WorkBundle managed section from `references/assets/template/AGENTS.md`; do not overwrite user-authored content outside the managed section.
- Create or preserve required `.gitignore` entries.
- Create or preserve the current project rule-store index at `.work-bundle/rules/index.yaml`; root `rules/index.yaml` is legacy-only and is not current project rule authority.
- Create the declared `.work-bundle/knowledge` structure without staging, committing, or initializing Git; Git ownership requires a separate explicitly authorized workflow.
- Bind registry IO to `references/assets/template/projects.yaml`; registry entries remain locators and project metadata owns working-state fields.
- Fail mechanically when a required reference asset is missing; do not invent fallback content.

**Validation scope:** mechanical checks only — file presence, directory structure, schema keys, registry status, metadata version, source repository fields, branch mismatch, stale baseline commit, registry/project repository ID mismatch, operation policy shape, CodeGraph metadata shape, and Git status. No semantic prose or bootstrap-artifact checks.

## Doctor Mode

Use `doctor-project` as the canonical doctor command.

- `doctor-project` without `--repair`: inspect and report mechanical failures only.
- `doctor-project --repair`: repair deterministic structure defects; default repair preserves existing non-empty user content.
- `doctor-project --repair --force`: repair with init-scoped template overwrite permission, while limiting `AGENTS.md` changes to the WorkBundle managed section.
- Every lifecycle result reports `git_actions: []`; initialization, doctor, metadata migration, and member provisioning never infer stage or commit authority.
- Report v3 workspace/member failures and v2 compatibility failures using machine-readable keys for stale metadata, missing repository state, branch/HEAD mismatch, stale baseline, registry/metadata mismatch, invalid operation policy, invalid workspace resources, and invalid CodeGraph shape.
- With `--repair --force`, refresh branch and commit baselines for all registered checkouts while preserving their IDs, paths, checkout roles, and unknown user fields.
- Do not rewrite user-authored project content without explicit `--force`.
- Do not migrate registry identity without preserving the old slug mapping or reporting the required user decision.

## Migration Mode

Use `migrate-project` only for unambiguous single-repository legacy layout upgrades. Use `migrate-to-multi-repository` when legacy evidence contains multiple repositories.

- Detect legacy `.work-bundle` layout, missing registry fields, obsolete template sections, retired bootstrap artifacts, legacy `rules/contract.yaml`, and moved template paths.
- Preserve existing knowledge notes, open questions, orchestration artifacts, Git history, and project identity.
- Add missing current files and directories without deleting unknown files.
- Preserve legacy metadata v1/v2 compatibility reads and provide explicit v2-to-v3 migration with `--dry-run` proposal, `--apply` conversion, origin/member mapping, conflict evidence, and unknown-field preservation.
- Convert legacy whole-file WorkBundle `AGENTS.md` template content to the current managed section when needed, preserving content outside managed sections.
- Write a migration report under `.work-bundle/orchestration/docs/migration-report-YYYY-MM-DD.md`.
- When retired legacy bootstrap artifacts are present, archive evidence under `.work-bundle/orchestration/docs/legacy-bootstrap-archive-YYYY-MM-DD/`, remove active legacy bootstrap paths, and list retired artifacts in the migration report.
- When legacy `rules/contract.yaml` is present, archive it under `.work-bundle/orchestration/docs/legacy-rules-contract-archive-YYYY-MM-DD/` and remove the active file.
- When legacy root `rules/index.yaml` is present, preserve it as a legacy artifact only; do not restore, overwrite, or validate it as current project rule authority.
- `migrate-project --force` applies migration-only structural repair; it does not broaden overwrite to general init-managed files.

## Must Not

- Load, create, require, validate, or reference retired legacy bootstrap artifacts or paths.
- Create or validate scripts; this skill consumes dispatcher commands only.
- Open, print, grep, serialize, copy, or migrate credential values; only structural credential-store validation is permitted.
- Create a managed worktree whose project root or Git common directory remains outside `workspace_root`.
- Eagerly scan all work-bundle skills, rules, or references beyond command output.
- Store project registry state under `project_root` or the work-bundle root.
- Delete existing knowledge, orchestration artifacts, registry data, or unknown user files.
- Create specifications, plans, phases, tasks, reviews, or handoffs during initialization.
- Stage, commit, reset, clean, stash, checkout, or otherwise mutate Git state from ordinary lifecycle commands.

## Output

- Initialized, doctored, validated, registered, or migrated project workspace.
- Updated bootstrap-resolved `projects.yaml` registry entry when registration runs.
- JSON command output with `status`, `failures`, registry status, metadata version/mode/resources/member evidence, redacted lifecycle transaction state, AGENTS sync evidence, and changed files where applicable. Compatibility reads retain existing v2 evidence fields until explicit migration.
- For `set-prefer-subagent`, JSON command output with `status`, `scope`, `prefer_subagent`, `target_path`, `changed_files`, and `effective_prefer_subagent`.
- Migration report and optional legacy-bootstrap archive paths under `.work-bundle/orchestration/docs/` when migration retires legacy artifacts.

## On Failure

- Stop before destructive changes.
- Report the blocking file, missing reference asset, registry entry, slug/mode decision, metadata schema defect, branch/HEAD mismatch, stale baseline, registry/metadata mismatch, workspace-resource defect, or CodeGraph inconsistency from command JSON `failures`.
- Ask at most one blocking question when slug or registry identity is unresolved.

## Runtime Rules

- `wb-project-context-preflight`: `rules/work-bundle/wb-project-context-preflight.md`
- `wb-project-registry`: `rules/work-bundle/wb-project-registry.md`
- `wb-script-instruction`: `rules/work-bundle/wb-script-instruction.md`
- `rule-work-bundle-security-exclusion`: `rules/security-exclusion.md`
- `wb-credential-use`: `rules/work-bundle/wb-credential-use.md` only when a task or utility requires a credential.
- `wb-migrate-to-multi-repository`: `rules/work-bundle/wb-migrate-to-multi-repository.md` only for explicit topology migration.
