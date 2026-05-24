---
name: execute-plan
description: 'Execute an implementation plan through scheduler-driven sub-agent delegation when available, with a single-agent fallback when delegation is unavailable or unsafe.'
---

# Execute Plan

Execute `${input:ExecutionTarget}` from `.work-bundle/orchestration/plan/`.

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

Verify the related spec, root plan, parent phase, selected task files, declared prerequisite tasks, required source files, resolved decisions, and required prior handoffs.

If anything blocks execution, stop and return the blocker format. Ask at most 2 blocking clarification questions. Use declared fallbacks instead of asking when available.

## Sub-Agent Scheduler Path

The main agent is the monitor, scheduler, and validator. It should not directly implement task work that was delegated.

1. Build the current execution queue from tasks whose dependencies are satisfied.
2. Partition the queue into waves of independent tasks with disjoint write scopes.
3. Delegate each task in the wave to a separate sub-agent when scopes allow parallel execution.
4. Give every sub-agent:
   - the assigned task path and relevant spec, plan, and phase paths;
   - allowed source and target files/modules;
   - exact validation required by the task;
   - instruction not to revert or overwrite other agents' work;
   - instruction to create an `executor-result` handoff before exit;
   - instruction to update its task status and the task status in the parent phase file before exit.
5. Wait for all sub-agents in the active wave to finish.
6. Validate each executor handoff against the task, parent phase, root plan, and source specification.
7. Accept only handoffs that include assigned task, files/symbols changed, validation evidence, deviations, unresolved issues, and next action.
8. If a handoff is valid and completion criteria are satisfied, mark the task `Completed`; if partial or blocked, mark `On Hold` or keep `In progress` with the blocker.
9. Refresh task status in the parent phase file and root plan task/phase indexes.
10. Continue with the next executable wave until the selected task, phase, or plan is complete or blocked.

When parallel tasks are possible, use multiple sub-agents. When tasks cannot safely run in parallel, delegate sequentially and record the reason.

## Single-Agent Fallback

Use this path when sub-agents are not supported or safe.

- Select the first executable task for the requested task, phase, or plan.
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
Files changed:
- <path or none>
Handoff: <path or required create-handoff action>
```

## Result Output

```text
Execution result: completed|partially-completed|failed
Target: <plan|phase|task id/path>
Execution path: sub-agent-scheduler|single-agent-fallback
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

Confirm no `.work-bundle/knowledge/` files were loaded or modified, only relevant execution artifacts were loaded, only task-scoped files changed, sub-agent support was checked, scheduler mode used multiple sub-agents when safe parallel work existed, fallback mode executed only one task, every sub-agent created an executor handoff and updated task status before exit, accepted handoffs were validated against task/phase/plan/spec, phase and plan handoffs were created when those targets completed, validation status is recorded, deviations and changed symbols are recorded, no more than 2 blocking questions were asked, and no archive operation occurred during execution.
