---
name: wb-initialize-project
description: Initialize, validate, doctor, or migrate a project-local work-bundle workspace via scripts/wb.py dispatcher commands.
---

# wb-initialize-project

## Purpose

Initialize, doctor, validate, register, inspect, or migrate a project as a work-bundle adapted workspace using mechanical dispatcher commands only.

## Inputs

- `project_root`: concrete project path.
- `~/.work-bundle/bootstrap.yaml` for `project_registry` and `work_bundle_root` resolution.
- `~/.work-bundle/bootstrap.yaml` field `prefer_subagent` for the global sub-agent scheduling preference default.
- `$project_root/.work-bundle/project.yaml` field `prefer_subagent` for the current workspace override.
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
| Initialize | `init-project <project-root> [--name <name>] [--force] [--dry-run] [--disable-work-bundle-git] [--create-project-skill-override]` |
| Doctor | `doctor-project <project-root> [--repair] [--force]` |
| Inspect only | `show-project [--project-root <project-root>]` |
| Strict validate | `validate-project <project-root> [--dry-run]` |
| Register only | `register-project <project-root> [--name <name>]` |
| Migrate | `migrate-project <project-root> [--name <name>] [--force]` |
| Set sub-agent preference | `set-prefer-subagent <true|false|enable|disable|on|off> --scope <global|project> [--project-root <project-root>]` |

`initialize-project` remains a compatibility alias for `init-project`; prefer `init-project` in new instructions.

**Preserve behavior (default):** commands preserve existing non-empty files and user-authored `AGENTS.md` content outside the WorkBundle managed section. Re-running `init-project` on a healthy project reports `changed_files: []`.

**`init-project --force`:** may overwrite init-managed template files only: `.work-bundle/project.yaml`, `.work-bundle/rules/index.yaml`, `.work-bundle/knowledge/project.yaml`. For `AGENTS.md`, force refreshes only the WorkBundle managed section from `references/assets/template/AGENTS.md` and preserves user-authored content outside that section.

**`migrate-project --force`:** narrower migration-only repair subset; overwrites `.work-bundle/project.yaml` only. For `AGENTS.md`, migration may convert legacy whole-file template content or stale managed sections to the current marker-bounded managed section without taking ownership of the whole file.

**`init-project --dry-run` / `validate-project --dry-run`:** inspect and report mechanical failures without writing project files.

**`prefer_subagent` management:**

- `prefer_subagent` is a boolean preference only; it does not bypass orchestration preflight, dependency, write-scope, handoff, or fallback rules.
- Effective value resolves as project metadata first, then global bootstrap, then `false`:
  - project: `$project_root/.work-bundle/project.yaml` -> `prefer_subagent`;
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
- On slug or project-root match, merge registry entries and preserve existing `aliases` and `source_repositories` unless explicitly replaced.
- Keep the registry locator-oriented. Registry `source_repositories` entries contain only stable `id`, `path`, `work_dir`, `remote`, and `git_repository`; they do not own `working_branch`, `last_commit_id`, `baseline_status`, `operation_policy`, or CodeGraph sync state.
- When registering a new repository to an existing workspace slug, update both the bootstrap-resolved registry and the workspace `.work-bundle/project.yaml`: append the locator to registry `source_repositories`, then add or refresh the corresponding project metadata `source_repositories[]` entry with mechanical Git and CodeGraph state.
- Carry a short role description in both registry output/templates and project metadata: the registry is locator-only; project metadata is the working-state authority for branch baseline, commit baseline, operation policy, and CodeGraph state.
- Ask for the workspace slug decision only when it is missing and blocking.

**Project metadata v2:**

- Render `.work-bundle/project.yaml` with `metadata_version: 2`.
- Keep `.work-bundle/project.yaml` as the project-local authority for operation policy, source repository working state, branch policy, Git baseline, and CodeGraph state.
- Render `source_repository_roles` describing the registry locator role and project metadata working-state authority role.
- Render `operation_policy.project_files` with non-destructive file operations and `operation_policy.git` with allowed read operations, permissive stage/commit/pull operations, and forbidden destructive operations including `reset --hard`, `clean -fd`, and `push --force`.
- Render `source_repositories[]` with stable `id`, absolute `path`, `work_dir`, `remote`, `git_repository`, `working_branch`, `branch_required`, `branch_check.required_before`, `branch_check.on_mismatch: stop`, `last_commit_id`, `baseline_status`, and nested `codegraph`.
- For Git-backed repositories, mechanically record current `working_branch` and `last_commit_id` when HEAD exists. Empty newly initialized repositories may use an empty `last_commit_id` with `baseline_status: unborn` until a later metadata refresh records a concrete commit.
- For non-Git repositories, set `git_repository: false`, `branch_required: false`, empty `last_commit_id`, and `baseline_status: not-git`.
- For repositories without `.codegraph/`, set `codegraph.supported: false`, `codegraph.index_present: false`, `codegraph.status: not-indexed`, and `codegraph.reason: no-index`. Do not run `codegraph init` or `codegraph sync`.
- For repositories with `.codegraph/`, report marker presence only; synchronization remains owned by orchestration review behavior, not initialization.

**Initialization structure:**

- Create `.work-bundle/knowledge/{context-packs,indexes,notes,open-questions}`.
- Create the full `.work-bundle/orchestration` subtree at initialization:
  - `orchestration/spec/{active,archived}`
  - `orchestration/plan/{active,archived}`
  - `orchestration/handoff/orchestration/{active,archived}`
  - `orchestration/handoff/executor/{active,archived}`
  - `orchestration/{docs,principles,templates,reviews,execution-state}`
- Directory membership is driven by `references/wb-initialize-project-default-work-bundle-tree.yaml`.
- Render `.work-bundle/project.yaml` from `references/assets/template/project.yaml`.
- Render `.work-bundle/project.yaml` with metadata v2 repository state from mechanical Git and `.codegraph/` inspection.
- Render `.work-bundle/project.yaml` with a `prefer_subagent: false` default unless a future template version explicitly changes the default.
- Render `.work-bundle/project.yaml` with an `agents_sync` section that owns WorkBundle `AGENTS.md` checksum and sync-status state.
- Create, append, or refresh `AGENTS.md` with the WorkBundle managed section from `references/assets/template/AGENTS.md`; do not overwrite user-authored content outside the managed section.
- Create or preserve required `.gitignore` entries.
- Create or preserve the current project rule-store index at `.work-bundle/rules/index.yaml`; root `rules/index.yaml` is legacy-only and is not current project rule authority.
- Initialize `.work-bundle/knowledge` as its own Git repository and create its initial deterministic commit when needed.
- Bind registry IO to `references/assets/template/projects.yaml`; registry entries remain locators and project metadata owns working-state fields.
- Fail mechanically when a required reference asset is missing; do not invent fallback content.

**Validation scope:** mechanical checks only — file presence, directory structure, schema keys, registry status, metadata version, source repository fields, branch mismatch, stale baseline commit, registry/project repository ID mismatch, operation policy shape, CodeGraph metadata shape, and Git status. No semantic prose or bootstrap-artifact checks.

## Doctor Mode

Use `doctor-project` as the canonical doctor command.

- `doctor-project` without `--repair`: inspect and report mechanical failures only.
- `doctor-project --repair`: repair deterministic structure defects; default repair preserves existing non-empty user content.
- `doctor-project --repair --force`: repair with init-scoped template overwrite permission, while limiting `AGENTS.md` changes to the WorkBundle managed section.
- Report metadata v2 failures using machine-readable failure keys such as stale metadata version, missing repository state, branch mismatch, stale baseline, registry/project mismatch, invalid operation policy, and invalid CodeGraph shape.
- Do not rewrite user-authored project content without explicit `--force`.
- Do not migrate registry identity without preserving the old slug mapping or reporting the required user decision.

## Migration Mode

Use `migrate-project` for legacy layout upgrades.

- Detect legacy `.work-bundle` layout, missing registry fields, obsolete template sections, retired bootstrap artifacts, legacy `rules/contract.yaml`, and moved template paths.
- Preserve existing knowledge notes, open questions, orchestration artifacts, Git history, and project identity.
- Add missing current files and directories without deleting unknown files.
- Upgrade legacy `metadata_version: 1` project metadata to `metadata_version: 2` by adding missing `operation_policy`, `source_repositories`, branch/commit baseline fields, and CodeGraph state while preserving unknown user fields.
- Convert legacy whole-file WorkBundle `AGENTS.md` template content to the current managed section when needed, preserving content outside managed sections.
- Write a migration report under `.work-bundle/orchestration/docs/migration-report-YYYY-MM-DD.md`.
- When retired legacy bootstrap artifacts are present, archive evidence under `.work-bundle/orchestration/docs/legacy-bootstrap-archive-YYYY-MM-DD/`, remove active legacy bootstrap paths, and list retired artifacts in the migration report.
- When legacy `rules/contract.yaml` is present, archive it under `.work-bundle/orchestration/docs/legacy-rules-contract-archive-YYYY-MM-DD/` and remove the active file.
- When legacy root `rules/index.yaml` is present, preserve it as a legacy artifact only; do not restore, overwrite, or validate it as current project rule authority.
- `migrate-project --force` applies migration-only structural repair; it does not broaden overwrite to general init-managed files.

## Must Not

- Load, create, require, validate, or reference retired legacy bootstrap artifacts or paths.
- Create or validate scripts; this skill consumes dispatcher commands only.
- Eagerly scan all work-bundle skills, rules, or references beyond command output.
- Store project registry state under `project_root` or the work-bundle root.
- Delete existing knowledge, orchestration artifacts, registry data, or unknown user files.
- Create specifications, plans, phases, tasks, reviews, or handoffs during initialization.

## Output

- Initialized, doctored, validated, registered, or migrated project workspace.
- Updated bootstrap-resolved `projects.yaml` registry entry when registration runs.
- JSON command output with `status`, `failures`, `registry_path`, `registry_entry` or `registry_status`, metadata v2 evidence such as `project_metadata_version`, `project_source_repositories`, `project_metadata_v2_failures`, `agents_status` or equivalent AGENTS sync evidence, and `changed_files` where applicable.
- For `set-prefer-subagent`, JSON command output with `status`, `scope`, `prefer_subagent`, `target_path`, `changed_files`, and `effective_prefer_subagent`.
- Migration report and optional legacy-bootstrap archive paths under `.work-bundle/orchestration/docs/` when migration retires legacy artifacts.

## On Failure

- Stop before destructive changes.
- Report the blocking file, missing reference asset, registry entry, slug decision, metadata v2 schema defect, branch mismatch, stale baseline, registry/project mismatch, or CodeGraph metadata inconsistency from command JSON `failures`.
- Ask at most one blocking question when slug or registry identity is unresolved.
