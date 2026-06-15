---
name: orch-execute-plan
description: 'Execute implementation plans through scheduler delegation or single-agent fallback.'
---

# orch-execute-plan

## Scope

Execute implementation plans through scheduler delegation or single-agent fallback.

## Workflow Reference

Use `references/assets/orchestration/workflow.md` as the shared workflow authority.

## Directive Reference

Load `references/directives/orchestration/execute-plan.md` for directive-specific behavior.

## Runtime Rules

- `orch-orchestration-boundary`: `rules/orchestration/orch-orchestration-boundary.md`
- `orch-execute-plan`: `rules/orchestration/orch-execute-plan.md`
- `orch-handoff-required`: `rules/orchestration/orch-handoff-required.md`

## Rule Loading (mandatory)

Before directive-specific work, read **every** rule listed in **Runtime Rules** from disk in full.

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
