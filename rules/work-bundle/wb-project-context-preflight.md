---
id: wb-project-context-preflight
applies_when:
  - a user request starts WorkBundle-guided work for a project repository
  - task requires source-code browsing, inspection, review, planning, repair, refactor, migration, or editing in a WorkBundle-registered project
  - task requires resolving workspace structure, member source repositories, work directories, project metadata, or repository structure before acting
  - orchestration workflow resolves project metadata before specification evidence, implementation planning, execution, review, or project scope updates
  - repository preflight evaluates source repositories from `.work-bundle/project.yaml`
  - agent checks branch baseline, commit baseline, registry locator, or CodeGraph support for a source repository
enforcement: must
load: conditional
requires: []
---

# Project Context Preflight

## Purpose

Require agents to resolve the containing `workspace_root` and establish each member repository state from `$workspace_root/.work-bundle/project.yaml` before using repository evidence, modifying source files, delegating execution, or reviewing implementation work.

## Must

- Resolve `work_bundle_config_root` as `~/.work-bundle/`.
- Read `$work_bundle_config_root/bootstrap.yaml` before resolving registry paths.
- Resolve the project registry path from `$work_bundle_config_root/bootstrap.yaml` field `project_registry` when registry access is required.
- Resolve an explicit `--workspace-root` first, or an explicit `--project-root` to its containing workspace; otherwise walk upward from cwd for `.work-bundle/project.yaml` before using bounded registry fallback.
- In single-repository compatibility mode, `$project_root/.work-bundle/project.yaml` is the same file because `project_root == workspace_root`; never apply that alias to a member root in multi-repository mode.
- Treat `$workspace_root/.work-bundle/project.yaml` as the authority for workspace mode, workspace resources, member bindings, source repository working state, operation policy, branch/HEAD observations, lifecycle state, and CodeGraph state.
- Treat `$work_bundle_config_root/registry/projects.yaml` as a locator only; it may identify workspace slug/root and stable repository origin `id`, `origin_path`, `remote`, and Git capability, but must not own expected branch, observed HEAD, cleanliness, lifecycle transaction, operation policy, or CodeGraph state.
- Establish a compact workspace/member map from workspace metadata before source inspection, planning, or edits, including `workspace_root`, mode, workspace resources, and each task-relevant member `project_root`.
- Treat metadata v2 as readable compatibility input. Do not silently relocate it, infer multi-repository topology, or create/move worktrees without explicit migration apply authority.
- Require explicit `single-repository` or `multi-repository` mode for new creation. Existing v3 metadata may supply its declared mode; v2 inspection never silently supplies a topology conversion decision.
- Inspect every applicable `source_repositories[]` entry before specification evidence collection, implementation planning, execution, review, and project-scope metadata updates.
- Treat each v3 `source_repositories[]` member binding, or v2 compatibility entry, as a separate `project_root` source boundary for preflight, CodeGraph checks, edits, validation, and delegation.
- For Git-backed repositories, compare actual `git branch --show-current` and `git rev-parse HEAD` evidence against v3 `expected_branch` and accepted `observed_head`, or v2 `working_branch` and `last_commit_id`, before trusting source evidence or editing files.
- For a managed worktree, verify `project_root` and absolute `git-common-dir` are under `workspace_root`; treat an external origin path as a read-only locator outside bounded provisioning or refresh.
- Block on branch mismatch, missing required repository metadata, stale commit baseline not explained by accepted executor-result handoffs, inaccessible repositories, unresolved Git status, or unexplained dirty status.
- Preserve accepted-handoff baseline semantics: only validated executor-result handoffs may explain expected dirty worktree changes during plan execution.
- For repositories without `.codegraph/`, record `no-index` or `not-indexed` fallback and do not initialize CodeGraph or run `codegraph sync`.
- For repositories with `.codegraph/`, apply `agent-codegraph-first` when the task requires source-code inspection, dependency tracing, planning, repair, refactor, migration, review, or editing.

## Must Not

- Do not infer active workspaces or source repositories from conversation memory when workspace metadata or the bootstrap-resolved registry is available.
- Do not treat the shell working directory as the full project boundary when project metadata lists additional source repositories.
- Do not inspect broad source trees before reading project metadata and establishing the compact project-structure map.
- Do not store branch/HEAD observations, cleanliness, lifecycle transactions, operation policy, or CodeGraph state in the global project registry.
- Do not write project registry state under `work_bundle_root` or `project_root`.
- Do not load durable knowledge files solely to satisfy project-structure awareness.
- Do not let `prefer_subagent` bypass project context preflight, branch baseline checks, dependency checks, write-scope checks, validation, handoff, or single-agent fallback rules.
- Do not run destructive Git operations such as cleanup, reset, stash, or force push to satisfy preflight.
- Do not initialize CodeGraph for a repository root that lacks `.codegraph/`.
- Do not infer lifecycle Git stage or commit authority from initialization, doctor, repair, migration, or validation authority.

## Validation

- Confirm project metadata was read from `$workspace_root/.work-bundle/project.yaml` before repository evidence collection, planning, execution, review, or project-scope metadata update.
- Confirm registry access, when needed, used the bootstrap-resolved `project_registry` path.
- Confirm the active workspace, workspace mode/resources, member project roots, source repository roles, and repository boundaries were identified from project metadata.
- Confirm Git-backed repositories recorded expected branch, actual branch, expected commit, actual commit, branch status, commit status, and accepted-baseline status.
- Confirm CodeGraph evidence records indexed or `no-index` state by repository and never initializes missing indexes.
- Confirm any bypass or fallback records the concrete reason in the task, phase, review, or executor-result handoff.

## On Violation

Stop before source investigation, file modification, delegation, review archive, or project metadata update. Report the missing metadata, registry mismatch, unresolved project structure, branch mismatch, stale baseline, dirty worktree, unresolved Git status, inaccessible repository, or CodeGraph policy violation, then rerun preflight after repair.
