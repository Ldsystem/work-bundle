---
name: orch-create-handoff
description: 'Create orchestration and executor-result handoffs for continuation or evidence.'
---

# orch-create-handoff

## Scope

Create orchestration and executor-result handoffs for continuation or evidence.

## Workflow Reference

Use `references/assets/orchestration/workflow.md` as the shared workflow authority.

## Context

Inspect relevant `.work-bundle/orchestration/` specs, plans, phases, tasks, previous handoffs, test results, and current execution state.

If accepted durable project knowledge is needed for an orchestration handoff outside execution completion, use `keep-summarizing` with `what-is-helpful` gateway mode and the `implementation_plan` retrieval policy. Do not directly browse `.work-bundle/knowledge/`.

Executor-result handoffs created during `execute-plan` must not retrieve durable knowledge. They may use only carried spec, plan, phase, task, declared handoff, and task-scoped source/test context.

Do not include raw chat logs, speculative reasoning, or unrelated history. Record missing, stale, contradictory, or uncertain context as assumptions, risks, or open questions.

## Types

- `orchestration`: planning, review, coordination, or conversation continuation.
- `executor-result`: implementation result from an executor agent to the orchestration agent.

Infer type from purpose when absent.

## Output Layout

```text
.work-bundle/orchestration/handoff/
  orchestration/active/handoff-orch-YYYYMMDD-001-[slug].md
  executor/active/handoff-exec-YYYYMMDD-001-[slug].md
  orchestration/archived/
  executor/archived/
  index.jsonl
```

Handoffs are orchestration artifacts, not durable project knowledge.

## Required Content

Every handoff includes:

- front matter and status badge;
- source context used;
- current state;
- completed and pending work;
- relevant files/artifacts;
- dependencies;
- risks, assumptions, open questions;
- validation/test evidence when applicable;
- executable next actions and completion criteria.

Executor-result handoffs also include assigned task, implementation summary, files/symbols changed, tests run, test results, deviations, unresolved issues, suggested durable conclusions, and recommended orchestration review.

## Hard Rules

- Do not store handoffs under `.work-bundle/knowledge/`.
- Do not implement source changes, edit application/test files, run migrations, apply patches, or execute plan tasks while creating a handoff.
- If the user also asks for implementation, finish the handoff artifact first, then stop and require an explicit `execute-plan` request.
- Do not include raw chat logs, private reasoning, or unrelated history.
- Do not present suggested durable conclusions as persisted knowledge.
- Stop if source artifact paths or current state are unknown.
- Executor-result handoffs must list changed files/symbols, validation, deviations, unresolved issues, and next action.

## Status and Index

Statuses:

```text
active | reviewed | archived | superseded
```

Update `.work-bundle/orchestration/handoff/index.jsonl` with `id`, `type`, `status`, `path`, `project`, `created_at`, `updated_at`, `related_spec`, `related_plan`, `related_phase`, and `related_task`. Use `null` for unavailable relationships.

## Contracts

Load only when creating or validating:

- `references/assets/orchestration/contract/handoff-orchestration-v1.md`
- `references/assets/orchestration/contract/handoff-executor-result-v1.md`

## Validation

Confirm required metadata and sections exist, referenced specs/plans/phases/tasks/files are listed, next actions are executable, unresolved decisions are explicit, executor-result fields are complete, raw chat is excluded, no handoff is written under `.work-bundle/knowledge/`, orchestration handoff durable knowledge came through `keep-summarizing`, and execution-completion handoffs did not invoke retrieval.

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
