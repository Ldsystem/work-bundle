---
id: wb-project-context-preflight
applies_when:
  - orchestration workflow resolves project metadata before specification evidence, implementation planning, execution, review, or project scope updates
  - repository preflight evaluates source repositories from `.work-bundle/project.yaml`
  - agent checks branch baseline, commit baseline, registry locator, or CodeGraph support for a source repository
enforcement: must
load: conditional
requires: []
---

# Project Context Preflight

## Purpose

Require agents to establish project-local repository context before using repository evidence, modifying source files, delegating execution, or reviewing implementation work.

## Must

- Resolve the project registry path from `$work_bundle_config_root/bootstrap.yaml` field `project_registry` when registry access is required.
- Treat `$project_root/.work-bundle/project.yaml` as the authority for source repository working state, operation policy, branch baseline, commit baseline, and CodeGraph state.
- Treat `$work_bundle_config_root/registry/projects.yaml` as a locator only; it may identify source repository `id`, `path`, `work_dir`, `remote`, and `git_repository`, but must not own `working_branch`, `last_commit_id`, `baseline_status`, `operation_policy`, or CodeGraph sync state.
- Inspect every applicable `source_repositories[]` entry before specification evidence collection, implementation planning, execution, review, and project-scope metadata updates.
- For Git-backed repositories, compare actual `git branch --show-current` and `git rev-parse HEAD` evidence against `working_branch` and `last_commit_id` before trusting source evidence or editing files.
- Block on branch mismatch, missing required repository metadata, stale commit baseline not explained by accepted executor-result handoffs, inaccessible repositories, unresolved Git status, or unexplained dirty status.
- Preserve accepted-handoff baseline semantics: only validated executor-result handoffs may explain expected dirty worktree changes during plan execution.
- For repositories without `.codegraph/`, record `no-index` or `not-indexed` fallback and do not initialize CodeGraph or run `codegraph sync`.
- For repositories with `.codegraph/`, apply `agent-codegraph-first` when the task requires source-code inspection, dependency tracing, planning, repair, refactor, migration, review, or editing.

## Must Not

- Do not infer active source repositories from conversation memory when project metadata or the bootstrap-resolved registry is available.
- Do not store branch baseline, commit baseline, operation policy, or CodeGraph sync state in the global project registry.
- Do not let `prefer_subagent` bypass project context preflight, branch baseline checks, dependency checks, write-scope checks, validation, handoff, or single-agent fallback rules.
- Do not run destructive Git operations such as cleanup, reset, stash, or force push to satisfy preflight.
- Do not initialize CodeGraph for a repository root that lacks `.codegraph/`.

## Validation

- Confirm project metadata was read from `$project_root/.work-bundle/project.yaml` before repository evidence collection, planning, execution, review, or project-scope metadata update.
- Confirm registry access, when needed, used the bootstrap-resolved `project_registry` path.
- Confirm Git-backed repositories recorded expected branch, actual branch, expected commit, actual commit, branch status, commit status, and accepted-baseline status.
- Confirm CodeGraph evidence records indexed or `no-index` state by repository and never initializes missing indexes.
- Confirm any bypass or fallback records the concrete reason in the task, phase, review, or executor-result handoff.

## On Violation

Stop before source investigation, file modification, delegation, review archive, or project metadata update. Report the missing metadata, registry mismatch, branch mismatch, stale baseline, dirty worktree, unresolved Git status, inaccessible repository, or CodeGraph policy violation, then rerun preflight after repair.
