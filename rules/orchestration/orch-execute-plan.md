---
id: orch-execute-plan
applies_when:
  - user invokes orch-execute-plan or the execute-plan directive
  - execute-plan resolves or begins an executable task or scheduler wave
enforcement: must
load: conditional
requires: []
---

# Execute Plan Execution Boundary

## Purpose

Bound plan execution to carried orchestration context and task-scoped project files. Execution consumes role context already present in specifications, plans, phases, tasks, and declared handoffs. It does not retrieve durable knowledge, archive artifacts, or perform review duties.

This rule applies **only** to `execute-plan`.

## Must

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
- Require every completed or blocked task, phase, and plan to produce an `executor-result` handoff through `create-handoff` before reporting completion.
- Update task, phase, and plan statuses coherently with validated handoff evidence.
- Ask at most 2 blocking clarification questions; use declared fallbacks instead of asking when available.
- Carry execution role context from upstream artifacts without invoking knowledge retrieval during execution.

## Must Not

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

## Validation

- Confirm repository preflight ran before selection, capability checks, delegation, or modification.
- Confirm every target source repository was resolved and recorded separately from the orchestration artifact repository.
- Confirm initial preflight passed and rechecks ran before each wave or fallback task.
- Confirm accepted baselines came only from validated executor-result handoffs.
- Confirm no repository cleanup or mutation was attempted to pass preflight.
- Confirm no `.work-bundle/knowledge/` files were loaded or modified.
- Confirm only relevant execution artifacts and task-scoped project files were used.
- Confirm scheduler mode used multiple sub-agents when safe parallel work existed and fallback mode executed only one task.
- Confirm executor handoffs, status updates, and phase or plan completion handoffs exist where required.
- Confirm no archive operation occurred during execution and no more than 2 blocking questions were asked.

## On Violation

Stop execution immediately, report the boundary or preflight violation with repository evidence, require the missing handoff or clean baseline, and do not mark the task, phase, or plan complete until execution boundary requirements are satisfied.
