---
name: orch-execute-plan
description: 'Execute implementation plans through scheduler delegation or single-agent fallback.'
---

# orch-execute-plan

## Scope

Execute implementation plans through visible-thread/worktree scheduler delegation or single-agent fallback.

## Workflow Reference

Use `references/assets/orchestration/workflow.md` as the shared workflow authority.

Prefer the smallest requested target: task, then phase, then plan. If given a task, execute that task only. If given a phase or plan and visible thread/worktree delegation is supported, the main agent acts as scheduler and advances through executable tasks until the selected target is complete or blocked. If visible thread/worktree delegation is unavailable, forbidden, or unsafe, use the single-agent fallback and execute one task only, or report a `delegation-visibility` blocker when fallback cannot satisfy the requested scope.

## Context Boundary

Allowed:

- referenced specs under `.work-bundle/orchestration/spec/`;
- active plans, phases, and tasks under `.work-bundle/orchestration/plan/`;
- explicitly referenced executor handoffs under `.work-bundle/orchestration/handoff/executor/`;
- source and test files directly required by executable tasks.

Forbidden:

- `.work-bundle/knowledge/`;
- raw chat logs;
- unrelated specs, plans, tasks, handoffs, or docs;
- broad repository exploration;
- architecture, API, data model, dependency, or durable-knowledge decisions not declared by the task.

Execution must use context already carried by the specification, plan, phase, task, and declared handoffs. Although `execute-plan` maps to the `execution` retrieval policy for upstream artifact preparation, execution itself must not run v3 retrieval queries, invoke `what-is-helpful`, or promote candidate/background notes while executing.

## Repository Preflight

Before execution selection, capability checks, delegation, or implementation-file modification:

1. Resolve every target source repository from the selected plan/phase/task write scopes, referenced project files, and canonical project metadata. Keep target source repositories distinct from the repository that contains orchestration artifacts.
   Classify each resolved target independently:
   - `target_kind=git-backed` with `preflight_kind=git-clean-worktree` when the target root is a Git worktree root;
   - `target_kind=local-project` with `preflight_kind=local-project` when an explicitly resolved local project root is accessible but is not Git-backed.
2. Run the read-only helper for the selected task files or explicit repositories:

   ```text
   python3 scripts/orch.py repository-preflight --task-file <task-path> [--task-file <task-path> ...]
   ```

3. Require every resolved Git-backed target repository to report `clean`. Block when no target repository resolves or any Git-backed target reports `dirty`, `unresolved`, or `inaccessible`. Do not reject an explicitly resolved non-Git local project root solely as `not-git`; require local-project evidence that records the absolute root path, source, accessibility, and that Git clean-worktree checks are not applicable.
4. Record the resolved target repository list, source, `target_kind`, `preflight_kind`, baseline, status, changed-path evidence for Git-backed targets, and local-project evidence for non-Git local project targets in blocked or result output.

The helper uses `git status --porcelain=v1 --untracked-files=all` only for Git-backed targets and is strictly read-only. It does not fabricate Git cleanliness evidence for local-project targets. Never automatically stash, commit, reset, restore, clean, delete, or otherwise alter pre-existing changes to pass preflight.

Recheck target repository cleanliness immediately before each scheduler wave and immediately before a single-agent fallback task begins. After accepting validated executor-result handoffs, build an accepted-baseline JSON object that maps each absolute repository path to the exact porcelain entries proven by those handoffs, then pass it with `--accepted-baseline <json-path>`. The accepted baseline explains only proven prior-wave/task outputs; any unrelated or unexplained current entry blocks further execution. Do not accept a baseline from an unvalidated handoff.

## CodeGraph Refresh

After repository preflight passes and before graph-derived inspection, delegation instructions, or implementation edits, decide CodeGraph applicability per target root.

- If the target root has no `.codegraph/`, record CodeGraph as skipped with reason `no-index` and use bounded fallback through direct file reads or text search. Do not initialize CodeGraph and do not run `codegraph sync`.
- If `.codegraph/` exists and CodeGraph is available, run `codegraph sync <absolute-repository-root>` after the applicable target preflight and before any graph-derived source inspection, broad browsing, delegation, or editing for that target. Then query CodeGraph for the task-relevant symbol, module, package, feature, or architectural area before broad browsing.
- If `codegraph sync <absolute-repository-root>` fails, record `sync-failed`, use bounded fallback for that repository, and block only when the task or user explicitly requires strict graph gating.
- Serialize `codegraph sync` operations for the same repository. Parallel scheduler waves may run implementation work only when no two tasks are syncing or querying the same repository index concurrently.
- For Git-backed targets, rerun repository preflight after a successful pre-inspection sync and before implementation begins. Any tracked or unignored change caused by sync is unexplained repository mutation and blocks execution. For local-project targets, rerun the local-project preflight evidence check after sync and record the post-sync accessibility state.
- When a task changes indexed source in a CodeGraph-enabled target, run a post-change `codegraph sync <absolute-repository-root>` before final graph impact validation and before the executor-result handoff. Record post-change sync as passed, failed, skipped, or not-applicable.
- Executor-result handoffs must record compact CodeGraph evidence by applicability. Include repository root, applicability, `up_to_date`, and required fallback or blocker facts such as `no-index`, `sync-failed`, `stale`, or `blocked`; add sync/query detail only when needed to explain a failure or indexed-source impact.

## Selection

Resolve target in order:

1. task ID/path -> execute that task only;
2. phase ID/path -> select all executable tasks in that phase, respecting dependencies;
3. plan ID/path -> select executable phases and tasks in dependency order;
4. no executable task -> report blocker and stop.

An executable task has status `Planned` or `In progress`, satisfied dependencies, resolved required decisions, available source files, and no missing required handoff.

## Capability Check

Before execution, determine whether the active agent environment supports visible thread/worktree delegation. A delegation surface is supported only when delegated plan, phase, or task ownership will run in a user-visible thread, visible worktree, or both, where the user can supervise the worker and inspect its context.

- Resolve effective `prefer_subagent` as project metadata first, then global bootstrap, then `false`: `.work-bundle/project.yaml` -> `prefer_subagent`, `$work_bundle_config_root/bootstrap.yaml` -> `prefer_subagent`, fallback `false`.
- Treat `prefer_subagent: true` only as permission to prefer the visible-thread/worktree scheduler when all existing safety checks pass.
- Treat `prefer_subagent: false` as a preference for single-agent fallback unless the user explicitly requests safe scheduler delegation for the current target.
- If effective `prefer_subagent` is `true`, visible thread/worktree delegation is supported, and the selected target has one or more safe executable tasks, use the sub-agent scheduler path.
- If effective `prefer_subagent` is `false`, visible thread/worktree delegation is unavailable, disabled by the user, blocked by the environment, or unsafe because scopes overlap or the next step depends on a single result, use the single-agent fallback.
- If visible thread/worktree delegation is unavailable or unsafe and single-agent fallback cannot satisfy the selected target, stop with a `delegation-visibility` blocker. Do not silently delegate to invisible internal spawn work.
- Do not fail only because visible delegation support is missing when single-agent fallback is valid. Record fallback reason in the result and handoff.
- Never allow `prefer_subagent` to bypass visible delegation safety, repository preflight, accepted-baseline checks, disjoint write scopes, dependency checks, handoff requirements, or the single-agent fallback.
- Invisible internal spawn workers must not own delegated plan, phase, or task implementation work. Internal workers may be used only for bounded helper analysis, local summarization, snippet comparison, or other support work that does not own delegated execution and does not replace visible thread/worktree task delegation.

## Preflight

After repository preflight passes, verify the related spec, root plan, parent phase, selected task files, declared prerequisite tasks, required source files, resolved decisions, and required prior handoffs.

If anything blocks execution, stop and return the blocker format. Ask at most 2 blocking clarification questions. Use declared fallbacks instead of asking when available.

## Sub-Agent Scheduler Path

The main agent is the monitor, scheduler, and validator. It should not directly implement task work that was delegated.

1. Build the current execution queue from tasks whose dependencies are satisfied.
2. Partition the queue into waves of independent tasks with disjoint write scopes.
3. Recheck every target repository for the wave against the initial or accepted-handoff baseline; block the entire wave on any unexplained change.
4. Delegate each task in the wave to a separate visible thread/worktree worker when scopes allow parallel execution. Before assignment, verify that the delegation surface is user-visible; if not, use single-agent fallback or stop with a `delegation-visibility` blocker.
5. Record the visible delegation reference for each task when the environment provides a thread id, worktree path, or user-visible label. Record `internal_spawn_used_for_task_delegation: false`.
6. Give every visible delegated worker:
   - the assigned task path and relevant spec, plan, and phase paths;
   - allowed source and target files/modules;
   - exact validation required by the task;
   - instruction not to revert or overwrite other agents' work;
   - instruction to use only visible thread/worktree task ownership and not invisible internal spawn work as the task delegation vehicle;
   - instruction that internal helpers are allowed only for bounded non-delegated support work;
   - instruction to record its visible thread/worktree reference when available and `internal_spawn_used_for_task_delegation: false` in the executor-result handoff;
   - instruction to verify its implementation against the related specification, root plan, parent phase, and assigned task before handoff;
   - instruction to repair every task-scoped drift or gap found by that verification, rerun the verification until no task-scoped drift or gap remains, and stop with an explicit blocker when repair would exceed task scope;
   - instruction to record explicit drift/gap verification evidence through compact `task_fit_check`, including artifacts checked, findings, repairs or clean result, recheck result, and any unresolved out-of-scope issue;
   - instruction to create a task-scoped sparse YAML `executor-result` handoff before exit, following `orch-handoff-required` and `references/assets/orchestration/contract/handoff-executor-result-v1.md`;
   - instruction to update its task status and the task status in the parent phase file before exit.
7. Wait for all visible delegated workers in the active wave to finish.
8. Validate each executor handoff against the task, parent phase, root plan, and source specification.
9. Accept only compact executor-result handoffs whose fields satisfy applicability rules: assigned task, result summary, changed files or inspected artifacts, validation evidence, unresolved blockers when present, `task_fit_check`, repository/preflight or accepted-baseline evidence when relevant, compact CodeGraph evidence when source-code work was in scope, and `delegation_evidence` when ownership was delegated or fallback proof is required.
10. If a handoff is valid and completion criteria are satisfied, mark the task `Completed`; if partial or blocked, mark `On Hold` or keep `In progress` with the blocker.
11. Refresh task status in the parent phase file and root plan task/phase indexes.
12. Build the next accepted-handoff baseline only from validated handoff evidence, then continue with the next executable wave until the selected task, phase, or plan is complete or blocked.

When parallel tasks are possible and visible thread/worktree delegation is safe, use multiple visible delegated workers. When tasks cannot safely run in parallel, delegate sequentially through visible surfaces or record the reason for single-agent fallback. Invisible internal spawn work is never a valid plan, phase, or task delegation vehicle.

## Single-Agent Fallback

Use this path when visible thread/worktree delegation is not supported or safe.

- Select the first executable task for the requested task, phase, or plan.
- Recheck every target repository for that task against the initial or accepted-handoff baseline immediately before implementation begins.
- Execute only that one task in the current conversation trip.
- Follow the task file exactly and modify only task-scoped files unless the task explicitly expands scope.
- Before handoff, verify the implementation against the related specification, root plan, parent phase, and selected task. Repair every task-scoped drift or gap, rerun the verification until it is clean, and record the same explicit drift/gap evidence required from delegated sub-agents. Stop with a blocker when repair would exceed task scope.
- Run declared validation when possible; otherwise report why it was skipped.
- Create or explicitly require a task-scoped sparse YAML `executor-result` handoff before exit. Execution-completion handoffs remain no-retrieval artifacts based only on carried spec, plan, phase, task, declared handoff, and task-scoped source/test context.
- Update the task status and the task status in the parent phase file when criteria are met or a blocker is known.
- Report the next executable task and stop.

This fallback preserves the original conservative workflow. Do not batch multiple tasks in one single-agent trip.

## Phase and Plan Completion

After valid task handoffs show all tasks in a phase are complete:

- validate phase completion criteria;
- update phase status to `Completed`;
- update the phase status in the root plan file;
- invoke `create-handoff` for a phase-scoped `executor-result` handoff;
- keep the phase handoff compact and applicability-based: completed tasks, changed or inspected artifacts, validation evidence, unresolved blockers when present, repository/CodeGraph/delegation evidence when relevant, and task-fit or phase-fit evidence sufficient for continuation.

After all phases in a plan are complete:

- validate plan completion criteria;
- update plan status to `Completed`;
- invoke `create-handoff` for a plan-scoped `executor-result` handoff;
- keep the plan handoff compact and applicability-based: completed phases, task handoff references, final validation evidence, unresolved blockers when present, repository/CodeGraph/delegation evidence when relevant, and plan-fit evidence sufficient for review.

Do not archive specs, plans, phases, tasks, or handoffs during execution. Archival belongs only to `review-plan`.

## Status

Use:

```text
Planned | In progress | Completed | Deprecated | On Hold
```

Do not mark a task, phase, or plan completed unless criteria are satisfied or incomplete validation is explicitly documented with a remediation path.

## Blocked Output

```text
Execution blocked.
Target: <plan|phase|task id/path>
Execution path: sub-agent-scheduler|single-agent-fallback
Blocker: <specific blocker>
Questions asked: <0|1|2>
Required action: <specific action>
Repository preflight:
- <absolute target repository> | source=<resolution source> | baseline=initial|accepted-handoff | status=dirty|unresolved|inaccessible|not-git | changes=<changed/staged/deleted/untracked or unexplained paths>
Delegation:
- delegated=<true|false> | surface=<visible-thread|visible-worktree|visible-thread-and-worktree|single-agent-fallback|none> | visible_reference=<thread id, worktree path, label, or not-provided> | internal_spawn_used_for_task_delegation=false | fallback_reason=<reason or null>
Files changed:
- <path or none>
Handoff: <path or required create-handoff action>
```

## Result Output

```text
Execution result: completed|partially-completed|failed
Target: <plan|phase|task id/path>
Execution path: sub-agent-scheduler|single-agent-fallback
Repository preflight:
- <absolute target repository> | source=<resolution source> | baseline=initial|accepted-handoff | status=clean|blocked
Delegation:
- delegated=<true|false> | surface=<visible-thread|visible-worktree|visible-thread-and-worktree|single-agent-fallback> | visible_reference=<thread id, worktree path, label, or not-provided> | internal_spawn_used_for_task_delegation=false | internal_workers_used_for_support=<true|false> | fallback_reason=<reason or null>
Executed:
- <task id/path>
Files changed:
- <path>
Validation:
- <test/command>: passed|failed|skipped
Handoffs:
- <path>
Status updates:
- <task|phase|plan id>: <status>
Continuation state: <completed target or next executable target when still in execution scope>
```

## Validation

Confirm repository preflight ran before selection/capability checks/delegation/modification, every target source repository was resolved and recorded separately from the orchestration artifact repository, every target passed initial preflight, rechecks ran before each wave or fallback task, accepted baselines came only from validated executor-result handoffs, unexplained changes blocked execution, no repository cleanup or mutation was attempted, no `.work-bundle/knowledge/` files were loaded or modified, only relevant execution artifacts were loaded, only task-scoped files changed, visible thread/worktree delegation support was checked, `prefer_subagent` remained permission-only and did not bypass visible delegation safety, scheduler mode used multiple visible delegated workers when safe parallel work existed, invisible internal spawn work did not own delegated plan/phase/task execution, fallback mode executed only one task or a `delegation-visibility` blocker was reported, internal helper workers were used only for bounded non-delegated support when present, every delegated or fallback executor verified its implementation against the related specification, root plan, parent phase, and task before handoff, every task-scoped drift or gap was repaired and rechecked, unresolved out-of-scope findings blocked completion, every executor handoff includes compact `task_fit_check` drift/gap verification evidence, every delegated executor created a sparse YAML executor handoff with `delegation_evidence` and updated task status before exit, accepted handoffs were validated against task/phase/plan/spec, phase and plan sparse executor-result handoffs were created when those targets completed, validation status is recorded, changed files or inspected artifacts are recorded, no forbidden executor advice fields are present, no more than 2 blocking questions were asked, and no archive operation occurred during execution.

## Runtime Rules

- `orch-orchestration-boundary`: `rules/orchestration/orch-orchestration-boundary.md`
- `orch-handoff-required`: `rules/orchestration/orch-handoff-required.md`

## Rule Loading (mandatory)

Before substantive execution work, read **every** rule listed in **Runtime Rules** from disk in full.

- **Must** load all cited rule files before substantive orchestration work.
- **Must** treat loaded rule Must, Must Not, Validation, and On Violation sections as binding for this skill session.
- **Must Not** rely on conversation memory, prior runs, or directive summaries as substitutes for cited rules.
- **Must** stop and reload rules when returning to an in-progress orchestration task after context compaction or handoff.

If a cited rule path is missing or unreadable, stop and report a rule-load blocker; do not proceed.

## Execution Constraints (skill-owned)

Bound plan execution to carried orchestration context and task-scoped project files. Execution consumes role context already present in specifications, plans, phases, tasks, and declared handoffs. It does not retrieve durable knowledge, archive artifacts, or perform review duties.

### Must

- Read only allowed execution context:
  - referenced specs under `.work-bundle/orchestration/spec/`;
  - active plans, phases, and tasks under `.work-bundle/orchestration/plan/`;
  - explicitly referenced executor handoffs under `.work-bundle/orchestration/handoff/executor/`;
  - source and test files directly required by executable tasks.
- Resolve every target source repository separately from the orchestration artifact repository before execution selection, capability checks, delegation, or implementation-file modification.
- Run read-only clean-worktree preflight for every resolved target repository and require initial `clean` status.
- Recheck target repository cleanliness immediately before each scheduler wave and immediately before a single-agent fallback task begins.
- Accept only validated executor-result handoffs as the next baseline; build accepted-baseline evidence only from proven handoff porcelain entries.
- Block on dirty, unresolved, inaccessible, or empty target sets; block on non-Git targets only when they lack explicit local-project evidence; block on unrelated or unexplained repository changes.
- Record resolved target repository list, source, `target_kind`, `preflight_kind`, baseline, status, changed-path evidence, and local-project evidence in blocked or result output.
- Check visible thread/worktree delegation support before delegation; use the sub-agent scheduler only when visible delegation is supported and safe, otherwise use single-agent fallback without failing only because visible delegation is unavailable.
- Partition independent tasks with disjoint write scopes into scheduler waves; delegate task work only to visible thread/worktree workers when parallel execution is safe.
- Execute only one task per conversation trip in single-agent fallback mode.
- Modify only task-scoped files unless the task explicitly expands scope.
- Require every completed or blocked task, phase, and plan to produce a compact `executor-result` handoff through `create-handoff` before reporting completion (handoff field requirements: follow `orch-handoff-required` and the executor-result contract).
- Require delegated and fallback executors to verify implementation against the related specification, root plan, parent phase, and task before handoff; repair and recheck every task-scoped drift or gap, block on out-of-scope findings, and record explicit verification evidence in the executor-result handoff.
- Update task, phase, and plan statuses coherently with validated handoff evidence.
- Ask at most 2 blocking clarification questions; use declared fallbacks instead of asking when available.
- Carry execution role context from upstream artifacts without invoking knowledge retrieval during execution.
- Preserve internal worker/helper use only for bounded non-delegated support work; it must not own delegated plan, phase, or task execution.

### Must Not

- Browse, load, modify, or retrieve `.work-bundle/knowledge/` during execution.
- Invoke `what-is-helpful`, run v3 retrieval queries, or promote candidate or background notes while executing.
- Archive specifications, plans, phases, tasks, or handoffs during execution; archival belongs only to `review-plan`.
- Automatically stash, commit, reset, restore, clean, delete, or otherwise mutate repositories to pass preflight.
- Use invisible internal spawn work as the plan, phase, or task delegation vehicle.
- Treat `prefer_subagent: true` as permission to bypass visible thread/worktree delegation safety.
- Treat orchestration artifact changes as source-repository dirt.
- Continue with no targets, dirty Git-backed targets, unresolved Git-backed targets, inaccessible targets, or non-Git targets that lack explicit local-project evidence.
- Accept a baseline from an unvalidated handoff.
- Batch multiple tasks in one single-agent fallback trip.
- Perform open-question gates, knowledge-update disposition evaluation, or review archive work during execution.
- Make architecture, API, data model, dependency, or durable-knowledge decisions not declared by the active task.

## Scripts

Use `scripts/orch.py` when deterministic helper behavior is needed.

## Boundary

Platform write boundary and durable-knowledge prohibition: follow `orch-orchestration-boundary` (`rules/orchestration/orch-orchestration-boundary.md`).

> **Deprecation:** The role-context subsystem is deprecated; see spec §0.9 in `spec-process-orch-skill-rule-boundary-optimization-20260611`. Do not invoke it from orch skills.
