---
name: orch-execute-plan
description: 'Execute implementation plans through scheduler delegation or single-agent fallback.'
---

# orch-execute-plan

## Scope

Execute implementation plans through scheduler delegation or single-agent fallback.

## Workflow Reference

Use `references/assets/orchestration/workflow.md` as the shared workflow authority.

Prefer the smallest requested target: task, then phase, then plan. If given a task, execute that task only. If given a phase or plan and sub-agents are supported, the main agent acts as scheduler and advances through executable tasks until the selected target is complete or blocked. If sub-agents are unavailable, forbidden, or unsafe, use the single-agent fallback and execute one task only.

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
2. Run the read-only helper for the selected task files or explicit repositories:

   ```text
   python3 scripts/orch.py repository-preflight --task-file <task-path> [--task-file <task-path> ...]
   ```

3. Require every resolved target repository to report `clean`. Block when no target repository resolves or any target reports `dirty`, `unresolved`, `inaccessible`, or `not-git`.
4. Record the resolved target repository list, source, baseline, status, and changed-path evidence in blocked or result output.

The helper uses `git status --porcelain=v1 --untracked-files=all` and is strictly read-only. Never automatically stash, commit, reset, restore, clean, delete, or otherwise alter pre-existing changes to pass preflight.

Recheck target repository cleanliness immediately before each scheduler wave and immediately before a single-agent fallback task begins. After accepting validated executor-result handoffs, build an accepted-baseline JSON object that maps each absolute repository path to the exact porcelain entries proven by those handoffs, then pass it with `--accepted-baseline <json-path>`. The accepted baseline explains only proven prior-wave/task outputs; any unrelated or unexplained current entry blocks further execution. Do not accept a baseline from an unvalidated handoff.

## Selection

Resolve target in order:

1. task ID/path -> execute that task only;
2. phase ID/path -> select all executable tasks in that phase, respecting dependencies;
3. plan ID/path -> select executable phases and tasks in dependency order;
4. no executable task -> report blocker and stop.

An executable task has status `Planned` or `In progress`, satisfied dependencies, resolved required decisions, available source files, and no missing required handoff.

## Capability Check

Before execution, determine whether the active agent environment supports sub-agents.

- If sub-agents are supported and the selected target has one or more executable tasks, use the sub-agent scheduler path.
- If sub-agents are unavailable, disabled by the user, blocked by the environment, or unsafe because scopes overlap or the next step depends on a single result, use the single-agent fallback.
- Do not fail only because sub-agent support is missing. Record fallback reason in the result and handoff.

## Preflight

After repository preflight passes, verify the related spec, root plan, parent phase, selected task files, declared prerequisite tasks, required source files, resolved decisions, and required prior handoffs.

If anything blocks execution, stop and return the blocker format. Ask at most 2 blocking clarification questions. Use declared fallbacks instead of asking when available.

## Sub-Agent Scheduler Path

The main agent is the monitor, scheduler, and validator. It should not directly implement task work that was delegated.

1. Build the current execution queue from tasks whose dependencies are satisfied.
2. Partition the queue into waves of independent tasks with disjoint write scopes.
3. Recheck every target repository for the wave against the initial or accepted-handoff baseline; block the entire wave on any unexplained change.
4. Delegate each task in the wave to a separate sub-agent when scopes allow parallel execution.
5. Give every sub-agent:
   - the assigned task path and relevant spec, plan, and phase paths;
   - allowed source and target files/modules;
   - exact validation required by the task;
   - instruction not to revert or overwrite other agents' work;
   - instruction to create an `executor-result` handoff before exit;
   - instruction to update its task status and the task status in the parent phase file before exit.
6. Wait for all sub-agents in the active wave to finish.
7. Validate each executor handoff against the task, parent phase, root plan, and source specification.
8. Accept only handoffs that include assigned task, files/symbols changed, validation evidence, deviations, unresolved issues, and next action.
9. If a handoff is valid and completion criteria are satisfied, mark the task `Completed`; if partial or blocked, mark `On Hold` or keep `In progress` with the blocker.
10. Refresh task status in the parent phase file and root plan task/phase indexes.
11. Build the next accepted-handoff baseline only from validated handoff evidence, then continue with the next executable wave until the selected task, phase, or plan is complete or blocked.

When parallel tasks are possible, use multiple sub-agents. When tasks cannot safely run in parallel, delegate sequentially and record the reason.

## Single-Agent Fallback

Use this path when sub-agents are not supported or safe.

- Select the first executable task for the requested task, phase, or plan.
- Recheck every target repository for that task against the initial or accepted-handoff baseline immediately before implementation begins.
- Execute only that one task in the current conversation trip.
- Follow the task file exactly and modify only task-scoped files unless the task explicitly expands scope.
- Run declared validation when possible; otherwise report why it was skipped.
- Create or explicitly require a task-scoped `executor-result` handoff before exit.
- Update the task status and the task status in the parent phase file when criteria are met or a blocker is known.
- Report the next executable task and stop.

This fallback preserves the original conservative workflow. Do not batch multiple tasks in one single-agent trip.

## Phase and Plan Completion

After valid task handoffs show all tasks in a phase are complete:

- validate phase completion criteria;
- update phase status to `Completed`;
- update the phase status in the root plan file;
- invoke `create-handoff` for a phase-scoped `executor-result` handoff;
- include completed tasks, validation evidence, deviations, blockers, and next executable phase or task.

After all phases in a plan are complete:

- validate plan completion criteria;
- update plan status to `Completed`;
- invoke `create-handoff` for a plan-scoped `executor-result` handoff;
- include phase summaries, task handoffs, validation evidence, deviations, blockers, and recommended `review-plan` action.

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
Next action: <next executable action or review-plan>
```

## Validation

Confirm repository preflight ran before selection/capability checks/delegation/modification, every target source repository was resolved and recorded separately from the orchestration artifact repository, every target passed initial preflight, rechecks ran before each wave or fallback task, accepted baselines came only from validated executor-result handoffs, unexplained changes blocked execution, no repository cleanup or mutation was attempted, no `.work-bundle/knowledge/` files were loaded or modified, only relevant execution artifacts were loaded, only task-scoped files changed, sub-agent support was checked, scheduler mode used multiple sub-agents when safe parallel work existed, fallback mode executed only one task, every sub-agent created an executor handoff and updated task status before exit, accepted handoffs were validated against task/phase/plan/spec, phase and plan handoffs were created when those targets completed, validation status is recorded, deviations and changed symbols are recorded, no more than 2 blocking questions were asked, and no archive operation occurred during execution.

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
- Block on dirty, unresolved, inaccessible, non-Git, or empty target sets and on unrelated or unexplained repository changes.
- Record resolved target repository list, source, baseline, status, and changed-path evidence in blocked or result output.
- Check sub-agent support before delegation; use the sub-agent scheduler when supported and safe, otherwise use single-agent fallback without failing only because sub-agents are unavailable.
- Partition independent tasks with disjoint write scopes into scheduler waves; delegate task work to sub-agents when parallel execution is safe.
- Execute only one task per conversation trip in single-agent fallback mode.
- Modify only task-scoped files unless the task explicitly expands scope.
- Require every completed or blocked task, phase, and plan to produce an `executor-result` handoff through `create-handoff` before reporting completion (handoff field requirements: follow `orch-handoff-required`).
- Update task, phase, and plan statuses coherently with validated handoff evidence.
- Ask at most 2 blocking clarification questions; use declared fallbacks instead of asking when available.
- Carry execution role context from upstream artifacts without invoking knowledge retrieval during execution.

### Must Not

- Browse, load, modify, or retrieve `.work-bundle/knowledge/` during execution.
- Invoke `what-is-helpful`, run v3 retrieval queries, or promote candidate or background notes while executing.
- Archive specifications, plans, phases, tasks, or handoffs during execution; archival belongs only to `review-plan`.
- Automatically stash, commit, reset, restore, clean, delete, or otherwise mutate repositories to pass preflight.
- Treat orchestration artifact changes as source-repository dirt.
- Continue with no targets or with dirty, unresolved, inaccessible, or not-git targets.
- Accept a baseline from an unvalidated handoff.
- Batch multiple tasks in one single-agent fallback trip.
- Perform open-question gates, knowledge-update disposition evaluation, or review archive work during execution.
- Make architecture, API, data model, dependency, or durable-knowledge decisions not declared by the active task.

## Scripts

Use `scripts/orch.py` when deterministic helper behavior is needed.

## Boundary

Platform write boundary and durable-knowledge prohibition: follow `orch-orchestration-boundary` (`rules/orchestration/orch-orchestration-boundary.md`).

> **Deprecation:** The role-context subsystem is deprecated; see spec §0.9 in `spec-process-orch-skill-rule-boundary-optimization-20260611`. Do not invoke it from orch skills.
