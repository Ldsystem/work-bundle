---
name: orch-create-implementation-plan
description: 'Create executable implementation plans, phases, and tasks from a specification.'
---

# orch-create-implementation-plan

## Scope

Create executable implementation plans, phases, and tasks from a specification.

## Workflow Reference

Use `references/assets/orchestration/workflow.md` as the shared workflow authority.

## Source Context

Load the related specification from `.work-bundle/orchestration/spec/` and treat it as the primary execution source. The spec must already carry accepted project knowledge.

Before creating any plan, inspect the source specification's `Open Questions` section. If it contains any unresolved open questions, refuse to create the implementation plan and return an actionable table with ID, question or uncertainty, blocking status, and required resolution. Planning may resume only after explicit user resolution and a revised specification.

Before creating any plan, inspect the source specification's `Knowledge Base Update` section. If the section is missing, treat the specification as incomplete, require spec repair, and stop before planning. Do not create a partial plan around a missing `Knowledge Base Update` section.

Use `keep-summarizing` with `what-is-helpful` gateway mode only when no sufficient spec exists or when repairing a spec before planning. Do not directly browse `.work-bundle/knowledge/`.

For v3 knowledge, map implementation planning to the `implementation_plan` retrieval policy. If source context includes retrieved notes, the plan must label them as `authority`, `candidate`, `background`, or `blocked`. Candidate, background, and blocked notes must not create executable tasks unless the related knowledge has been promoted into authority in the source specification.

## Execution Chain

```text
spec -> plan -> phase -> task -> execute -> handoff
```

Downstream executors may read only the related spec, root plan, relevant phase, relevant task, declared prior handoffs, and task-scoped source/test files. They must not read `.work-bundle/knowledge/`.

## Requirements

- Convert the spec into deterministic phases, tasks, dependencies, affected files/modules, validation, completion criteria, and handoff requirements.
- Carry required execution context from spec into the root plan, each phase, and each task by referencing stable spec IDs and adding only task-specific execution detail.
- Carry the source spec `Knowledge Base Update` disposition, expected durable conclusions, evidence-source expectations, and follow-up path into the root plan, final task or review criteria, and executor-result handoff requirements.
- Add leading clarification or spec-repair tasks only when the source specification has no unresolved open questions but still lacks stable IDs, paths, validation details, or file-level execution context.
- Use explicit IDs, paths, statuses, dependencies, commands, validation rules, and completion criteria.
- Do not create handoff files directly; require `create-handoff`.
- Do not store plans under `.work-bundle/knowledge/`.

## Role Separation

Plans must preserve strict artifact roles:

- **Specification**: stable requirements, constraints, interfaces, data contracts, acceptance criteria, alternatives, and open questions.
- **Root plan**: execution strategy, sequencing, phase map, risk handling, validation strategy, desired files, and dependency graph.
- **Phase**: a bounded execution milestone that groups related tasks and lists only the spec IDs, decisions, files, and tests needed by those tasks.
- **Task**: one executable unit with exact source files, target files, target symbols, implementation steps, validation, completion criteria, and handoff requirement.

Do not embed the implementation plan inside the specification. Do not make phase or task files read like new specifications.

## Anti-Duplication Rules

These rules are mandatory:

- Root plans may summarize spec intent once, but must not copy long spec sections.
- Phase files must reference requirement IDs such as `REQ-003`, `AC-004`, `CON-002`, `OQ-001`, and `API-001` instead of repeating their full text.
- Task files must reference the exact spec IDs they implement or validate, then provide only concrete file-level instructions.
- If a phase or task repeats more than a short one-line summary of a requirement, replace it with a spec-ID reference.
- If a downstream executor needs the full requirement text, it must read the related specification listed in `source_spec`; do not paste the full requirement text into the task.
- If a requirement has no stable ID in the source spec, create a leading spec-repair task before planning dependent implementation work.
- If a phase or task cannot be executed from the related spec plus its own file-level instructions, repair the task. Do not solve this by copying large spec sections.

## Hard Rules

- Stop if no related spec exists and the user did not ask for spec repair.
- Stop if the related spec contains unresolved open questions, even when the answer appears obvious.
- Stop if the related spec omits `Knowledge Base Update`; return a spec repair requirement before planning.
- Do not implement source changes, edit application/test files, run migrations, apply patches, or execute any planned task while creating the plan.
- If the user also asks for implementation, finish the plan artifact first, then stop and require an explicit `execute-plan` request.
- Do not make executor tasks depend on future knowledge retrieval.
- Do not hide uncertainty inside task instructions; create clarification/spec-repair tasks first.
- Do not infer answers silently, pick an unresolved alternative, downgrade blocking questions, or create a partial plan for unresolved scope.
- Do not create tasks without dependencies, validation, completion criteria, and handoff requirement.
- Do not create tasks that duplicate specification prose instead of citing spec IDs.
- Do not create phases or tasks without exact source files, target files, target symbols, validation instructions, and relevant spec-ID references.
- Do not create phases or tasks whose target files are `.work-bundle/knowledge/**`; those writes belong to `ks-*` skills after orchestration review or explicit knowledge follow-up.
- Do not use broad globs such as `src/**` as the only source or target path for a task. A broad directory may appear only when paired with exact files or a narrow symbol-level explanation.
- Do not write raw chat logs, unsupported facts, or durable knowledge notes.

## Output Layout

```text
.work-bundle/orchestration/plan/
  active/[purpose]-[component]-[version].md
  active/[plan-id]/phase-001-[slug].md
  active/[plan-id]/phase-001-[slug]/task-001-[slug].md
  archived/
  index.jsonl
```

Purpose prefixes: `upgrade`, `refactor`, `feature`, `data`, `infrastructure`, `process`, `architecture`, `design`.

## Required Content

Root plan:

- related specification;
- carried execution context as a compact spec-ID map, not duplicated spec prose;
- a carried `Knowledge Base Update` summary with disposition, expected durable conclusions, evidence sources, and required follow-up path from the source specification;
- requirements, constraints, source references, alternatives, open questions, risks by ID and execution impact;
- phase index;
- desired files/modules;
- tests and completion criteria, including the final knowledge-update disposition gate.

Each phase:

- subset of spec IDs required for the phase;
- phase-specific decisions, dependencies, task index, tests, completion criteria.
- no copied spec sections beyond short one-line summaries.

Each task:

- exact self-contained execution context based on cited spec IDs;
- goals, dependencies, source files, target files, target symbols;
- implementation instructions, validation, completion criteria, and executor-result handoff requirements that carry any expected durable conclusions or explicit `none`.
- no copied spec sections beyond short one-line summaries.

## IDs and Status

Use stable prefixes such as `REQ-`, `CON-`, `PAT-`, `DATA-`, `API-`, `ALT-`, `OQ-`, `TEST-`, `DONE-`, `phase-`, and `task-`.

Plan, phase, and task statuses:

```text
Planned | In progress | Completed | Deprecated | On Hold
```

## Mandatory Handoff Delegation

Every generated root plan, phase, and task must instruct executor agents to invoke `create-handoff` and create an `executor-result` handoff before reporting completed or blocked status.

Required boundaries:

- end of each completed or blocked task;
- end of each completed or blocked phase;
- end of the completed or blocked root plan.

Each completion criteria section must include a `DONE-HANDOFF-*` item naming `create-handoff`, type `executor-result`, and scope `task`, `phase`, or `plan`.

Pass available plan id/path, phase id/path, task id/path, related spec path, status, completed work, changed files/symbols, tests, deviations, unresolved issues, suggested durable conclusions, and recommended next actions to `create-handoff`.
If the source spec `Knowledge Base Update` section says no durable update is expected, require handoffs to report explicit `none` for suggested durable conclusions and cite the evidence that supports that outcome.

## Contracts

Load only when creating or validating:

- `references/assets/orchestration/contract/plan-v1.md`
- `references/assets/orchestration/contract/phase-v1.md`
- `references/assets/orchestration/contract/task-v1.md`

## Validation

Confirm required front matter and sections exist, the source specification includes `Knowledge Base Update`, paths and dependencies are explicit, execution context is carried forward through spec-ID references plus concrete file-level instructions, no executor is required to read `.work-bundle/knowledge/`, blockers become leading clarification/spec-repair tasks, no phase or task targets `.work-bundle/knowledge/**`, indexes are updated, and every plan/phase/task has mandatory `executor-result` handoff criteria that carry suggested durable conclusions or explicit `none`.

Reject and repair the plan if:

- a phase or task duplicates long specification prose;
- a phase or task lacks relevant spec IDs;
- a task lacks exact source files, target files, target symbols, validation, or handoff criteria;
- the plan blurs specification requirements with execution ordering;
- an executor would need to infer target files or dependencies from broad prose.

## Runtime Rules

- `orch-orchestration-boundary`: `rules/orchestration/orch-orchestration-boundary.md`
- `orch-knowledge-gateway`: `rules/orchestration/orch-knowledge-gateway.md`
- `orch-open-questions`: `rules/orchestration/orch-open-questions.md`
- `orch-artifact-authoring`: `rules/orchestration/orch-artifact-authoring.md`
- `orch-review-completion`: `rules/orchestration/orch-review-completion.md`

## Rule Loading (mandatory)

Before substantive planning work, read **every** rule listed in **Runtime Rules** from disk in full.

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
