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
- Carry the source spec `Knowledge Base Update` disposition, evidence-source expectations, and review follow-up path into the root plan, final task or review criteria, and executor-result handoff requirements.
- After generating the root plan, phase files, and task files, run a generated-plan verification pass against the source specification before reporting completion.
- The generated-plan verification pass must check exact artifact paths, source-spec ID coverage, dependencies, safe parallelization opportunities, task write scopes, validation commands, and `create-handoff` completion requirements.
- Repair generated-artifact drift, missing coverage, dependency mistakes, unsafe parallelization, validation gaps, handoff gaps, and internal consistency problems in the same planning turn, then repeat verification until no generated-artifact gap remains or a source-spec defect blocks progress.
- Add leading clarification or spec-repair tasks only when the source specification has no unresolved open questions but still lacks stable IDs, paths, validation details, or file-level execution context.
- Use explicit IDs, paths, statuses, dependencies, commands, validation rules, and completion criteria.
- Do not create handoff files directly; require `create-handoff`.
- Do not store plans under `.work-bundle/knowledge/`.

## How to make tasks parallel

Use this guidance only for task boundaries; keep the pattern names and rationale out of executor-facing prose unless they are needed as task-fit evidence.

- Create or confirm a stable boundary artifact before branching parallel tasks. If no boundary artifact exists, keep the work serialized.
- Use the smallest boundary artifact that separates responsibility cleanly:
  - `api-contract-first` for API shape shared between caller and implementation.
  - `port-interface-first` for core behavior behind a stable port before adapters or implementations branch.
  - `repository-contract-first` for persistence ownership split behind a repository interface or query contract.
  - `DTO/schema-first` for request, response, persistence, event, or pipeline data shape.
  - `event-schema-first` for producers and consumers that can branch after the emitted event payload is stable.
  - `facade-first` for callers and implementation internals separated by a narrow facade.
  - `strategy/rule-matrix-first` for behavior variants that can branch after the decision table is stable.
  - `command-contract-first` for command handlers, CLI actions, jobs, or workflow steps with a stable input/output contract.
  - `pipeline-stage-contract-first` for adjacent pipeline stages separated by stage input/output contracts.
  - `state-table-first` for stateful workflows whose branches can depend on an agreed state and transition table.
  - `branch-by-abstraction` for replacing behavior while old and new implementations coexist behind an abstraction.
  - `expand-and-contract` for staged schema or API changes that require compatible expansion before cleanup.
  - `schema-contract-first` for general schema-shaped artifacts when the more specific DTO, event, command, or pipeline strategy does not fit.
  - `interface-stub-first` for core logic behind a simple interface stub when no richer boundary is needed.
  - `fixture-contract-first` for contract tests, golden data, or shared mock inputs.
  - `adapter-boundary-first` for a split between core logic and concrete adapters.
  - `documentation-or-reference-first` for a short reference, example, or other shared guidance artifact.
  - `validation-convergence` for the final integration task that proves branches still fit together.
- Give each parallel task exact source files, target files, dependencies, allowed and forbidden files, and validation.
- Reject parallelization when tasks share target files, unresolved decisions, migration ordering, or validation ownership.
- Require a convergence task any time separately built branches must be integrated and validated.

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
- Do not report planning completion while generated plan, phase, or task artifacts still drift from the source specification, omit required spec IDs, contain inconsistent paths or dependencies, lack safe parallelization notes, or lack validation and handoff requirements.
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
- a carried `Knowledge Base Update` summary with disposition, evidence sources, and required review follow-up path from the source specification;
- requirements, constraints, source references, alternatives, open questions, risks by ID and execution impact;
- phase index;
- desired files/modules;
- generated-artifact verification evidence showing source-spec coverage, exact paths, dependencies, safe parallelization, validation, and handoff requirements were checked and repaired before completion;
- tests and completion criteria, including the final knowledge-update disposition gate.

Each phase:

- subset of spec IDs required for the phase;
- phase-specific decisions, dependencies, task index, tests, completion criteria.
- phase-level generated-artifact verification expectations for spec-ID alignment, dependencies, task ordering, safe parallelization, validation, and handoff requirements.
- no copied spec sections beyond short one-line summaries.

Each task:

- exact self-contained execution context based on cited spec IDs;
- goals, dependencies, source files, target files, target symbols;
- implementation instructions, validation, completion criteria, and executor-result handoff requirements that carry compact continuation and review evidence.
- generated-artifact integrity expectations for exact files, dependencies, validation, handoff requirements, and required same-turn repair when the task artifact is incomplete or inconsistent.
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

Require compact sparse YAML executor-result handoffs by applicability. Include only continuation and review evidence needed for the completed or blocked scope: related spec/plan/phase/task identity, result state, concise summary, changed or inspected files/symbols, validation commands and results, unresolved blockers when present, `task_fit_check` or phase/plan fit evidence, repository/preflight evidence, compact CodeGraph evidence when applicable, and `delegation_evidence` when ownership was delegated or fallback proof is required.

Carry `Knowledge Base Update` disposition only as review evidence for `orch-review-plan` resolution through approved `ks-*` skills. Do not make executors provide durable-knowledge advice or direct knowledge writes in handoff payloads. If the source spec says no durable update is expected, carry that disposition and the supporting source-spec evidence as review disposition evidence.

Omit empty sections and forbidden executor-result advice fields. Use `unresolved` and fit-check findings for remaining issues, and keep durable knowledge persistence decisions in the review stage.

## Contracts

Load only when creating or validating:

- `references/assets/orchestration/contract/plan-v1.md`
- `references/assets/orchestration/contract/phase-v1.md`
- `references/assets/orchestration/contract/task-v1.md`

## Validation

Confirm required front matter and sections exist, the source specification includes `Knowledge Base Update`, paths and dependencies are explicit, execution context is carried forward through spec-ID references plus concrete file-level instructions, no executor is required to read `.work-bundle/knowledge/`, blockers become leading clarification/spec-repair tasks, no phase or task targets `.work-bundle/knowledge/**`, indexes are updated, and every plan/phase/task has mandatory compact sparse YAML `executor-result` handoff criteria using only applicable continuation and review evidence.

Run generated-plan verification before reporting completion:

- compare the root plan, every phase, and every task back to the source specification's stable IDs, resolved alternatives, open-question decisions, constraints, affected files, validation expectations, and handoff requirements;
- confirm exact paths, dependencies, task ordering, safe parallelization flags, source files, target files, target symbols, validation commands, and completion criteria are internally consistent across root plan, phases, and tasks;
- repair generated-artifact drift, missing coverage, duplicate spec prose, invalid dependencies, unsafe or missing parallelization notes, validation gaps, and handoff gaps in the same turn;
- stop for specification repair instead of patching around the issue when the source specification itself has unresolved questions, missing stable IDs, missing evidence, or contradictory instructions.

Reject and repair the plan if:

- a phase or task duplicates long specification prose;
- a phase or task lacks relevant spec IDs;
- a task lacks exact source files, target files, target symbols, validation, or handoff criteria;
- the plan blurs specification requirements with execution ordering;
- an executor would need to infer target files or dependencies from broad prose.
- generated-plan verification finds artifact drift, coverage gaps, path or dependency inconsistencies, unsafe parallelization, missing validation, or missing handoff requirements.

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
