---
id: wb-project-context-preflight
applies_when:
  - a user request starts WorkBundle-guided work for a project repository
  - task requires source-code browsing, inspection, review, planning, repair, refactor, migration, or editing in a WorkBundle-registered project
  - task requires resolving workspace structure, member source repositories, work directories, project metadata, or repository structure before acting
  - orchestration workflow resolves project metadata before specification evidence, implementation planning, execution, review, or project scope updates
  - repository preflight evaluates metadata-v4 portable repositories together with device-local bindings
  - agent checks branch baseline, commit baseline, registry locator, or CodeGraph support for a source repository
enforcement: must
load: conditional
requires: []
---

# Project Context Preflight

## Purpose

Require agents to resolve the containing `workspace_root`, portable topology, and version-appropriate local repository authority before using repository evidence, modifying source files, delegating execution, or reviewing implementation work.

## Must

- Resolve `work_bundle_config_root` as `~/.work-bundle/`.
- Read `$work_bundle_config_root/bootstrap.yaml` before resolving registry paths.
- Resolve the project registry path from `$work_bundle_config_root/bootstrap.yaml` field `project_registry` when registry access is required.
- Resolve an explicit `--workspace-root` first, or an explicit `--project-root` to its containing workspace; otherwise walk upward from cwd for `.work-bundle/project.yaml` before using bounded registry fallback.
- In single-repository compatibility mode, `$project_root/.work-bundle/project.yaml` is the same file because `project_root == workspace_root`; never apply that alias to a member root in multi-repository mode.
- For metadata v4, treat `$workspace_root/.work-bundle/project.yaml` as portable project/topology authority for stable workspace identity, mode, source-repository identity, canonical remotes, root/member topology, materialization requirements, and portable operation policy.
- For metadata v4, resolve device-local workspace root, control-plane checkout observations, member `project_root` paths, checkout kinds, observed branch/HEAD/time, and Git common directories only from `device_bindings` in the bootstrap-resolved `project_registry`.
- For metadata v3, preserve `$workspace_root/.work-bundle/project.yaml` as local working-state authority only during explicit v3 reads and migrations.
- Establish a compact workspace/member map from v4 portable metadata plus its matching device binding, or from explicit v3 metadata during compatibility work, before source inspection, planning, or edits.
- Treat metadata v2 as readable compatibility input. Do not silently relocate it, infer multi-repository topology, or create/move worktrees without explicit migration apply authority.
- Require explicit `single-repository` or `multi-repository` mode for new creation. Existing v3 metadata may supply its declared mode; v2 inspection never silently supplies a topology conversion decision.
- Inspect every applicable `source_repositories[]` entry before specification evidence collection, implementation planning, execution, review, and project-scope metadata updates.
- Treat each v4 portable repository joined to its device binding, each v3 `source_repositories[]` member binding, or each v2 compatibility entry as a separate `project_root` source boundary for preflight, CodeGraph checks, edits, validation, and delegation.
- For Git-backed repositories, compare live Git evidence with portable v4 branch policy and device-local observations, v3 `expected_branch` and accepted `observed_head`, or v2 `working_branch` and `last_commit_id`, according to the metadata version being read.
- Carry verified repository structure, branch/HEAD, baseline, and CodeGraph evidence into the as-is evidence of the current Truth Basis. If portable topology, device-local observations, live Git, or expected delta conflict materially, stop through the existing repository- or decision-blocked route before source edits.
- For a managed worktree, verify `project_root` and absolute `git-common-dir` are under `workspace_root`; treat an external origin path as a read-only locator outside bounded provisioning or refresh.
- Block on branch mismatch, missing required repository metadata, stale commit baseline not explained by accepted executor-result handoffs, inaccessible repositories, unresolved Git status, or unexplained dirty status.
- Preserve accepted-handoff baseline semantics: only validated executor-result handoffs may explain expected dirty worktree changes during plan execution.
- For repositories without `.codegraph/`, record `no-index` or `not-indexed` fallback and do not initialize CodeGraph or run `codegraph sync`.
- For repositories with `.codegraph/`, apply `agent-codegraph-first` when the task requires source-code inspection, dependency tracing, planning, repair, refactor, migration, review, or editing.

## Must Not

- Do not infer active workspaces or source repositories from conversation memory when workspace metadata or the bootstrap-resolved registry is available.
- Do not treat the shell working directory as the full project boundary when project metadata lists additional source repositories.
- Do not inspect broad source trees before reading project metadata and establishing the compact project-structure map.
- Do not store metadata-v4 local checkout paths or observations in portable `project.yaml`; store them only in the matching bootstrap-resolved `device_bindings` entry.
- Do not apply the metadata-v3 project-local authority model to metadata v4.
- Do not write project registry state under `work_bundle_root` or `project_root`.
- Do not load durable knowledge files solely to satisfy project-structure awareness.
- Do not let `prefer_subagent` bypass project context preflight, branch baseline checks, dependency checks, write-scope checks, validation, handoff, or single-agent fallback rules.
- Do not run destructive Git operations such as cleanup, reset, stash, or force push to satisfy preflight.
- Do not initialize CodeGraph for a repository root that lacks `.codegraph/`.
- Do not infer lifecycle Git stage or commit authority from initialization, doctor, repair, migration, or validation authority.

## Validation

- Confirm metadata v4 portable topology was read from `$workspace_root/.work-bundle/project.yaml` and local paths/observations were read from the matching bootstrap-resolved `device_bindings` entry before repository evidence collection, planning, execution, or review.
- Confirm the Truth Basis cites verified portable topology and device-local observations without moving local fields into v4 project metadata.
- Confirm registry access, when needed, used the bootstrap-resolved `project_registry` path.
- Confirm the active workspace, mode, portable repositories, local member project roots, and repository boundaries were identified from the correct authority for the active metadata version.
- Confirm Git-backed repositories recorded expected branch, actual branch, expected commit, actual commit, branch status, commit status, and accepted-baseline status.
- Confirm CodeGraph evidence records indexed or `no-index` state by repository and never initializes missing indexes.
- Confirm any bypass or fallback records the concrete reason in the task, phase, review, or executor-result handoff.

## On Violation

Stop before source investigation, file modification, delegation, review archive, or project metadata update. Report the missing metadata, registry mismatch, unresolved project structure, branch mismatch, stale baseline, dirty worktree, unresolved Git status, inaccessible repository, or CodeGraph policy violation, then rerun preflight after repair.
