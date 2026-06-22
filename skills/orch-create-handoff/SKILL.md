---
name: orch-create-handoff
description: 'Create compact executor-result handoffs for continuation or evidence.'
---

# orch-create-handoff

## Scope

Create compact executor-result handoffs for continuation or evidence. Orchestration handoffs are legacy artifacts only and are not created by the active workflow.

## Workflow Reference

Use `references/assets/orchestration/workflow.md` as the shared workflow authority.

## Context

Inspect relevant `.work-bundle/orchestration/` specs, plans, phases, tasks, previous executor-result handoffs, test results, and current execution state.

Executor-result handoffs created during `execute-plan` must not retrieve durable knowledge. They may use only carried spec, plan, phase, task, declared handoff, and task-scoped source/test context.

Do not include raw chat logs, speculative reasoning, or unrelated history. Record missing, stale, contradictory, or uncertain context as assumptions, risks, or open questions.

## Types

- `executor-result`: implementation result from an executor agent to the orchestration agent.
- `orchestration`: legacy-only historical handoff type. Do not create new active orchestration handoffs from this workflow.

Infer type from purpose when absent.

## Output Layout

```text
.work-bundle/orchestration/handoff/
  executor/active/handoff-exec-YYYYMMDD-001-[slug].yaml
  orchestration/archived/
  executor/archived/
  index.jsonl
```

Handoffs are orchestration artifacts, not durable project knowledge.

Use sparse YAML by default for executor-result handoffs. Existing archived Markdown handoffs remain legacy-compatible and indexable; do not convert them unless explicitly scoped.

## Required Content

Executor-result handoffs follow `rules/orchestration/orch-handoff-required.md` and `references/assets/orchestration/contract/handoff-executor-result-v1.md`.

Always include identity, related artifacts, result state, and concise summary. Include other fields only when applicable for continuation or review:

- `changes.files` for changed or inspected files, symbols, artifacts, schemas, commands, or docs.
- `validation.commands` for commands, tests, inspections, or intentional skips.
- `unresolved` only for remaining blockers or issues.
- `task_fit_check` for completed or partial task results, covering the related specification, root plan, parent phase, and assigned task.
- `repository` when repository preflight, accepted baseline, changed paths, or blocker state matters.
- `codegraph` when source-code inspection or edits were in scope; keep it to `root`, `applicable`, `up_to_date`, and fallback/blocker facts unless more detail is needed.
- `delegation_evidence` when task, phase, or plan ownership was delegated or fallback proof is required; record `internal_spawn_used_for_task_delegation: false`.

## Hard Rules

- Do not store handoffs under `.work-bundle/knowledge/`.
- Do not create new active `handoff-orch-*` artifacts or offer orchestration handoff creation as an active workflow path.
- Do not implement source changes, edit application/test files, run migrations, apply patches, or execute plan tasks while creating a handoff.
- If the user also asks for implementation, finish the handoff artifact first, then stop and require an explicit `execute-plan` request.
- Do not include raw chat logs, private reasoning, or unrelated history.
- Do not include durable-knowledge recommendations, orchestration review recommendations, executor advice fields, or strategy advice in executor-result handoffs.
- Stop if source artifact paths or current state are unknown.
- Executor-result handoffs must list changed files or inspected artifacts, validation, unresolved blockers when present, and compact `task_fit_check` when applicable.
- Executor-result handoffs must not omit applicable `codegraph:` or `delegation_evidence:` and must not record contradictory delegation evidence such as `internal_spawn_used_for_task_delegation: true`.

## Status and Index

Statuses:

```text
active | reviewed | archived | superseded
```

Update `.work-bundle/orchestration/handoff/index.jsonl` with `id`, `type`, `status`, `path`, `project`, `created_at`, `updated_at`, `related_spec`, `related_plan`, `related_phase`, and `related_task`. Use `null` for unavailable relationships.

## Contracts

Load only when creating or validating:

- `references/assets/orchestration/contract/handoff-executor-result-v1.md`
- `references/assets/orchestration/contract/handoff-orchestration-v1.md` only for explicit legacy validation of existing orchestration handoffs.

## Validation

Confirm required sparse YAML metadata exists, referenced specs/plans/phases/tasks/files are listed when applicable, unresolved blockers are explicit when present, executor-result fields are complete by applicability rather than fixed section presence, forbidden executor advice fields are absent, applicable `codegraph:` evidence includes compact up-to-date or fallback/blocker facts, delegated executor-result handoffs include `delegation_evidence:`, `visible_reference` when available, and `internal_spawn_used_for_task_delegation: false`, raw chat is excluded, no handoff is written under `.work-bundle/knowledge/`, no active orchestration handoff is created, and execution-completion handoffs did not invoke retrieval.

## Runtime Rules

- `orch-orchestration-boundary`: `rules/orchestration/orch-orchestration-boundary.md`
- `orch-artifact-authoring`: `rules/orchestration/orch-artifact-authoring.md`
- `orch-handoff-required`: `rules/orchestration/orch-handoff-required.md`

## Rule Loading (mandatory)

Before substantive handoff work, read **every** rule listed in **Runtime Rules** from disk in full.

- **Must** load all cited rule files before substantive orchestration work.
- **Must** treat loaded rule Must, Must Not, Validation, and On Violation sections as binding for this skill session.
- **Must Not** rely on conversation memory, prior runs, or directive summaries as substitutes for cited rules.
- **Must** stop and reload rules when returning to an in-progress orchestration task after context compaction or handoff.

If a cited rule path is missing or unreadable, stop and report a rule-load blocker; do not proceed.

## Scripts

Use `scripts/orch.py` when deterministic helper behavior is needed.

## Additional References

- `references/assets/orchestration/contract/`

## Boundary

Platform write boundary and durable-knowledge prohibition: follow `orch-orchestration-boundary` (`rules/orchestration/orch-orchestration-boundary.md`).

> **Deprecation:** The role-context subsystem is deprecated; see spec §0.9 in `spec-process-orch-skill-rule-boundary-optimization-20260611`. Do not invoke it from orch skills.
